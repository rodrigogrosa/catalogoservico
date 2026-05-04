import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.local_llm_service import LocalLlmService
from app.services.snapmaker_profile_service import SnapmakerProfileService


router = APIRouter()

# Cache simples para evitar I/O externo a cada health check do load balancer
_llm_cache: dict[str, object] = {}
_LLM_CACHE_TTL_SECONDS = 60


def _git_commit() -> str:
    """Retorna hash curto do commit atual (7 chars).

    1. BUILD_COMMIT env var (injetada via ARG no Dockerfile)
    2. Arquivo .build_commit (escrito pelo RUN no Dockerfile)
    3. subprocess git (só funciona em dev local)
    """
    # 1. Env var direta
    env_commit = os.environ.get("BUILD_COMMIT", "").strip()
    if env_commit and env_commit != "unknown":
        return env_commit[:7]

    # 2. Arquivo gravado no build
    try:
        commit_file = os.environ.get("BUILD_COMMIT_FILE", "/app/backend/.build_commit")
        val = Path(commit_file).read_text().strip()
        if val and val != "unknown":
            return val[:7]
    except Exception:  # noqa: BLE001
        pass

    # 3. Fallback git (dev local)
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


@router.get("/health")
async def health() -> dict[str, object]:
    """Health check leve — sem I/O externo. Usado pelo load balancer e Docker healthcheck."""
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "pipeline_version": settings.pipeline_version,
        "git_commit": _git_commit(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/health/full")
async def health_full() -> dict[str, object]:
    """Health check completo com status do LLM e perfil Snapmaker. Sob demanda."""
    settings = get_settings()
    profile = SnapmakerProfileService().load_profile()

    now = perf_counter()
    if (now - float(_llm_cache.get("_ts", 0))) > _LLM_CACHE_TTL_SECONDS:
        llm = LocalLlmService(settings=settings)
        _llm_cache["runtime"] = llm.describe_runtime()
        _llm_cache["_ts"] = now

    return {
        "status": "ok",
        "environment": settings.app_env,
        "storage_root": str(settings.storage_root),
        "snapmaker_profile": settings.snapmaker_profile_name,
        "pipeline_version": settings.pipeline_version,
        "slicer_target": profile["slicer_target"],
        "llm_runtime": _llm_cache.get("runtime"),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def readiness() -> dict[str, object]:
    settings = get_settings()
    profile_service = SnapmakerProfileService()
    try:
        profile = profile_service.load_profile()
        probe = Path(settings.storage_root) / ".readiness_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Readiness failed: {exc}") from exc

    return {
        "status": "ready",
        "storage_root": str(settings.storage_root),
        "pipeline_version": settings.pipeline_version,
        "slicer_target": profile.get("slicer_target"),
    }
