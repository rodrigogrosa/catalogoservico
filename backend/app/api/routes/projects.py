import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.auth import require_current_user_or_query_token, require_permission
from app.schemas.auth import AuthUser
from fastapi.responses import JSONResponse

from app.schemas.project import (
    ImportUrlRequest,
    JobStatusResponse,
    ProcessProjectRequest,
    ProjectBundleResponse,
    ProjectPrintFileResponse,
    ProjectCompareResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectSummary,
    UpdateProjectRequest,
    UploadJobAccepted,
)
from app.services.dependencies import get_project_service
from app.services.project_service import ProjectService
from app.services import upload_queue as uq


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(default=1, ge=1, description="Página (1-based)"),
    per_page: int = Query(default=20, ge=1, le=200, description="Itens por página"),
    status: str | None = Query(default=None, description="Filtrar por status"),
    search: str | None = Query(default=None, description="Buscar por nome"),
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.view")),
) -> ProjectListResponse:
    logger.info("projects_list_requested", extra={"username": current_user.username, "page": page, "per_page": per_page})
    result = service.list_projects(page=page, per_page=per_page, status_filter=status, search=search)
    return ProjectListResponse(**result)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.view")),
) -> ProjectDetailResponse:
    logger.info("project_detail_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.delete")),
) -> dict[str, str]:
    logger.info("project_delete_requested", extra={"username": current_user.username, "project_id": project_id})
    try:
        deleted = service.delete_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return {"status": "deleted", "project_id": project_id}


@router.patch("/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> ProjectDetailResponse:
    logger.info("project_update_requested", extra={"username": current_user.username, "project_id": project_id})
    result = service.update_project(project_id, payload.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return result


@router.post("/{project_id}/previews/upload", response_model=ProjectDetailResponse)
async def upload_preview_photo(
    project_id: str,
    file: UploadFile = File(...),
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> ProjectDetailResponse:
    """Upload a new photo file directly into the project's previews folder."""
    logger.info("preview_upload_requested", extra={"username": current_user.username, "project_id": project_id})
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Máximo 20 MB.")
    try:
        return service.add_preview_photo(project_id, file.filename or "photo.jpg", content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}/previews", response_model=ProjectDetailResponse)
async def delete_preview_photo(
    project_id: str,
    path: str = Query(..., description="Caminho relativo da foto, ex: /storage/slug/id/previews/foto.jpg"),
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> ProjectDetailResponse:
    """Delete a preview photo from disk and remove it from the project manifest."""
    logger.info("preview_delete_requested", extra={"username": current_user.username, "project_id": project_id, "path": path})
    try:
        return service.delete_preview_photo(project_id, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/backfill-catalog", response_model=dict)
async def backfill_catalog(
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> dict:
    logger.info("catalog_backfill_requested", extra={"username": current_user.username})
    return service.backfill_sales_profiles()


@router.post("/rename-all", response_model=dict)
async def rename_all_projects(
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> dict:
    """Re-generate Portuguese commercial names for all projects."""
    logger.info("rename_all_requested", extra={"username": current_user.username})
    return await asyncio.to_thread(service.rename_all_projects)


@router.get("/{project_id}/progress")
async def stream_project_progress(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_current_user_or_query_token),
) -> StreamingResponse:
    """SSE endpoint that streams processing progress for a project.

    Token can be passed as ?token= query param because EventSource (browser)
    does not support custom headers.
    """
    from app.services.project_service import _progress_store

    async def generate():
        for _ in range(600):  # max 5 minutes at 0.5s intervals
            data = _progress_store.get(project_id, {})
            yield f"data: {json.dumps(data)}\n\n"
            if data.get("done"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_upload_job(
    job_id: str,
    current_user: AuthUser = Depends(require_permission("projects.create")),
) -> JobStatusResponse:
    """Poll the status of an async upload job."""
    data = uq.get_job_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return JobStatusResponse(
        job_id=job_id,
        status=data.get("status", "unknown"),
        project_id=data.get("project_id") or None,
        error=data.get("error") or None,
        created_at=data.get("created_at") or None,
        updated_at=data.get("updated_at") or None,
    )


@router.post("/upload")
async def upload_project(
    files: list[UploadFile] = File(...),
    project_name: str | None = Form(default=None),
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.create")),
):
    """Upload one or more project files.

    When Redis is available the job is queued asynchronously and the endpoint
    returns HTTP 202 with a ``job_id`` for polling via GET /projects/jobs/{job_id}.
    When Redis is not configured (local dev without REDIS_URL) the upload is
    processed synchronously and the full ProjectDetailResponse is returned (HTTP 200).
    """
    import uuid  # noqa: PLC0415

    logger.info(
        "project_upload_requested",
        extra={
            "username": current_user.username,
            "project_name": project_name,
            "file_count": len(files),
            "filenames": [upload.filename for upload in files],
        },
    )
    try:
        # Always save files to disk first — fast local I/O, keeps the binary out of Redis.
        saved_files, layout = await service.save_upload_files(files, project_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    payload = {
        "type": "upload",
        "job_id": job_id,
        "project_name": layout.get("version_name", project_name or "projeto-3d"),
        "saved_files": [str(p) for p in saved_files],
        "layout": {
            **{k: v for k, v in layout.items() if k != "folders"},
            "folders": {k: str(v) for k, v in layout.get("folders", {}).items()},
        },
        "origin_url": None,
    }
    queued = uq.enqueue_upload_job(job_id, payload)
    if queued:
        poll_url = f"/api/v1/projects/jobs/{job_id}"
        return JSONResponse(
            status_code=202,
            content=UploadJobAccepted(job_id=job_id, status="queued", poll_url=poll_url).model_dump(),
        )
    # Fallback: Redis unavailable — process synchronously
    try:
        result = await asyncio.to_thread(
            service.create_project_from_saved_files,
            saved_files,
            layout,
            layout.get("version_name", project_name or "projeto-3d"),
            None,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import-url")
async def import_project_url(
    payload: ImportUrlRequest,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.create")),
):
    """Import a project from a direct download URL.

    Returns HTTP 202 + job_id when Redis is available, or HTTP 200 + project
    when running without Redis (synchronous fallback).
    """
    import uuid  # noqa: PLC0415

    logger.info(
        "project_import_url_requested",
        extra={
            "username": current_user.username,
            "project_name": payload.project_name,
            "url": payload.url,
        },
    )
    job_id = uuid.uuid4().hex
    job_payload = {
        "type": "import_url",
        "job_id": job_id,
        "url": payload.url,
        "project_name": payload.project_name or "",
    }
    queued = uq.enqueue_upload_job(job_id, job_payload)
    if queued:
        poll_url = f"/api/v1/projects/jobs/{job_id}"
        return JSONResponse(
            status_code=202,
            content=UploadJobAccepted(job_id=job_id, status="queued", poll_url=poll_url).model_dump(),
        )
    # Fallback: process synchronously
    try:
        return await service.create_project_from_url(payload.url, requested_name=payload.project_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/process", response_model=ProjectSummary)
async def process_project(
    project_id: str,
    payload: ProcessProjectRequest,
    background_tasks: BackgroundTasks,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> ProjectSummary:
    logger.info("project_process_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    if project.status == "processing":
        raise HTTPException(status_code=409, detail="Projeto ja esta em processamento. Aguarde concluir ou atualize o status.")

    background_tasks.add_task(service.process_project, project_id, payload)
    current = project.model_dump()
    current["status"] = "processing"
    return ProjectSummary(**current)


@router.post("/{project_id}/refresh-previews", response_model=ProjectDetailResponse)
async def refresh_project_previews(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> ProjectDetailResponse:
    logger.info("project_refresh_previews_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.refresh_previews(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return project


@router.get("/{project_id}/bundle", response_model=ProjectBundleResponse)
async def build_project_bundle(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.download")),
) -> ProjectBundleResponse:
    logger.info("project_bundle_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return service.build_bundle(project_id)


@router.get("/{project_id}/print-file", response_model=ProjectPrintFileResponse)
async def get_project_print_file(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.download")),
) -> ProjectPrintFileResponse:
    logger.info("project_print_file_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    try:
        artifact = service.build_print_file(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectPrintFileResponse(print_file=artifact)


@router.get("/{project_id}/compare/{other_project_id}", response_model=ProjectCompareResponse)
async def compare_projects(
    project_id: str,
    other_project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.view")),
) -> ProjectCompareResponse:
    logger.info(
        "project_compare_requested",
        extra={"username": current_user.username, "project_id": project_id, "other_project_id": other_project_id},
    )
    try:
        return service.compare_projects(project_id, other_project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/reprocess", response_model=ProjectDetailResponse)
async def reprocess_project(
    project_id: str,
    payload: ProcessProjectRequest,
    background_tasks: BackgroundTasks,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.process")),
) -> ProjectDetailResponse:
    """Create a new version from existing original files and start the pipeline.

    The user does *not* need to re-upload the source file.  The original files
    are copied to the new version directory automatically.
    """
    logger.info("project_reprocess_requested", extra={"username": current_user.username, "project_id": project_id})
    try:
        new_project = await asyncio.to_thread(service.create_reprocess_version, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(service.process_project, new_project.id, payload)
    return new_project


@router.get("/{project_id}/versions", response_model=list[ProjectSummary])
async def list_project_versions(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.view")),
) -> list[ProjectSummary]:
    """Return all stored versions for the same slug, newest first."""
    logger.info("project_versions_requested", extra={"username": current_user.username, "project_id": project_id})
    return service.list_project_versions(project_id)
