"""SnapMaker3d – Projects Read Microservice
==========================================
Serves GET /api/v1/projects and GET /api/v1/projects/{project_id}.

Architecture
------------
* Layer 1  –  Redis cache (TTL 5s detail / 15s list).  ~1 ms response.
* Layer 2  –  Direct JSON file reads from NFS on cache miss.  ~5-20 ms.
* No ProjectService, no SQLAlchemy, no heavy pipeline imports.
* Stateless: can run as N replicas behind nginx; all share the same Redis.
* When Redis is unavailable the service falls back to NFS reads (graceful
  degradation).

Routing handled by nginx (see infra/nginx/api-gateway.conf):
  GET  /api/v1/projects          → this service
  GET  /api/v1/projects/{id}     → this service
  *    /api/v1/projects/**       → backend writer
  *    everything else           → backend
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.auth import require_permission
from app.core import redis_cache
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas.auth import AuthUser
from app.schemas.project import (
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectSummary,
)

configure_logging()
logger = logging.getLogger("svc.projects.read")
settings = get_settings()
ROOT: Path = settings.storage_root
ROOT_STR: str = str(ROOT)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SnapMaker3d – Projects Read Service",
    version="1.0.0",
    description="Dedicated read service for GET /projects. Backed by Redis + NFS.",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",
}


@app.middleware("http")
async def security_and_logging(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    try:
        response = await call_next(request)
        for h, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(h, v)
        return response
    except Exception as exc:
        logger.exception("unhandled_error path=%s request_id=%s", request.url.path, request_id)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    return {"status": "ok", "service": "projects-reader"}


# ---------------------------------------------------------------------------
# GET /api/v1/projects  (list)
# ---------------------------------------------------------------------------

@app.get("/api/v1/projects", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: AuthUser = Depends(require_permission("projects.view")),
) -> ProjectListResponse:
    # --- Layer 1: Redis ---
    cached = await redis_cache.get_list_async(ROOT_STR, page, per_page, status, search)
    if cached is not None:
        logger.debug("list_cache_hit page=%d", page)
        return ProjectListResponse(**cached)

    # --- Layer 2: NFS scan ---
    logger.debug("list_cache_miss page=%d – scanning NFS", page)
    all_items = await anyio.to_thread.run_sync(_scan_summaries)

    # Filter
    filtered = all_items
    if status:
        filtered = [m for m in filtered if m.get("status") == status]
    if search:
        s = search.lower()
        filtered = [
            m for m in filtered
            if s in m.get("name", "").lower() or s in m.get("id", "").lower()
        ]

    total = len(filtered)
    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    page_items = filtered[offset: offset + per_page]

    payload: dict[str, Any] = {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
    # Warm Redis so the next request is served from cache
    await redis_cache.set_list_async(ROOT_STR, page, per_page, status, search, payload)

    return ProjectListResponse(**payload)


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}  (detail)
# ---------------------------------------------------------------------------

@app.get("/api/v1/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    current_user: AuthUser = Depends(require_permission("projects.view")),
) -> ProjectDetailResponse:
    # Reject path traversal early
    sanitized = Path(project_id).name
    if sanitized != project_id or ".." in project_id or "/" in project_id or "\\" in project_id:
        raise HTTPException(status_code=400, detail="project_id inválido.")

    # --- Layer 1: Redis ---
    cached = await redis_cache.get_project_async(ROOT_STR, project_id)
    if cached is not None:
        logger.debug("detail_cache_hit id=%s", project_id)
        try:
            return ProjectDetailResponse(**cached)
        except Exception:
            # Stale schema in cache – ignore and re-read
            pass

    # --- Layer 2: NFS ---
    logger.debug("detail_cache_miss id=%s – reading NFS", project_id)
    data = await anyio.to_thread.run_sync(_read_project, project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

    # Warm Redis
    await redis_cache.set_project_async(ROOT_STR, project_id, data)

    return ProjectDetailResponse(**data)


# ---------------------------------------------------------------------------
# NFS helpers (run in thread to avoid blocking the event loop)
# ---------------------------------------------------------------------------

def _read_project(project_id: str) -> dict[str, Any] | None:
    """O(1) read: derives path from slug convention, falls back to glob."""
    match = re.match(r"^(.+)_v(\d+)$", project_id)
    if match:
        slug = match.group(1)
        project_dir = ROOT / slug / project_id
        manifest_file = project_dir / "project.json"
        if manifest_file.exists():
            return _load_and_normalize(manifest_file, project_dir)

    # Legacy fallback
    for project_dir in ROOT.glob(f"*/{project_id}"):
        manifest_file = project_dir / "project.json"
        if manifest_file.exists():
            return _load_and_normalize(manifest_file, project_dir)

    return None


def _load_and_normalize(manifest_file: Path, project_dir: Path) -> dict[str, Any] | None:
    """Read project.json and normalise storage paths to /storage/ URLs."""
    try:
        data: dict[str, Any] = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("json_read_failed path=%s: %s", manifest_file, exc)
        return None

    data["storage_path"] = str(project_dir)

    # Normalize absolute NFS paths on input_files to portable paths
    known_dirs = {
        "original": project_dir / "original",
        "processado": project_dir / "processado",
        "export": project_dir / "export",
        "previews": project_dir / "previews",
        "relatorios": project_dir / "relatorios",
        "logs": project_dir / "logs",
    }
    for item in data.get("input_files", []):
        p = Path(str(item.get("path", "")))
        if p.exists():
            continue
        replacement = known_dirs["original"] / p.name
        if replacement.exists():
            item["path"] = str(replacement)

    # Normalise preview_url and other absolute path fields to /storage/ URLs
    for field in ("preview_url",):
        val = data.get(field)
        if val and ROOT_STR in str(val):
            try:
                rel = Path(str(val)).relative_to(ROOT)
                data[field] = f"/storage/{rel.as_posix()}"
            except ValueError:
                pass

    # Lightweight manifest stub (avoids NFS read of project_manifest.json)
    if data.get("manifest") is None and data.get("has_project_manifest"):
        data["manifest"] = {
            "project_id": data.get("id", ""),
            "project_name": data.get("name", ""),
            "slug": data.get("slug", ""),
            "version": data.get("version", 1),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "source_ecosystem": data.get("source_ecosystem", "generic"),
            "pipeline_version": "stored",
        }

    return data


def _scan_summaries() -> list[dict[str, Any]]:
    """Glob all project.summary.json (or project.json) and return deduped list."""
    manifests: list[dict[str, Any]] = []

    for project_dir in ROOT.glob("*/*"):
        if not project_dir.is_dir():
            continue
        summary_file = project_dir / "project.summary.json"
        manifest_file = project_dir / "project.json"
        source = summary_file if summary_file.exists() else manifest_file
        if not source.exists():
            continue
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            manifests.append(data)
        except Exception:
            continue

    # Keep only latest version per slug
    by_slug: dict[str, dict[str, Any]] = {}
    for item in manifests:
        slug = item.get("slug")
        if not slug:
            continue
        existing = by_slug.get(slug)
        if existing is None or int(item.get("version") or 0) > int(existing.get("version") or 0):
            by_slug[slug] = item

    return sorted(by_slug.values(), key=lambda x: str(x.get("updated_at", "")), reverse=True)
