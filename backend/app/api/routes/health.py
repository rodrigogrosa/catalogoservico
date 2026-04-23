from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.local_llm_service import LocalLlmService
from app.services.snapmaker_profile_service import SnapmakerProfileService


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    llm = LocalLlmService(settings=settings)
    profile = SnapmakerProfileService().load_profile()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "storage_root": str(settings.storage_root),
        "snapmaker_profile": settings.snapmaker_profile_name,
        "pipeline_version": settings.pipeline_version,
        "slicer_target": profile["slicer_target"],
        "llm_runtime": llm.describe_runtime(),
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
