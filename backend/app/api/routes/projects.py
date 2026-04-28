import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.auth import require_permission
from app.schemas.auth import AuthUser
from app.schemas.project import (
    ImportUrlRequest,
    ProcessProjectRequest,
    ProjectBundleResponse,
    ProjectPrintFileResponse,
    ProjectCompareResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectSummary,
)
from app.services.dependencies import get_project_service
from app.services.project_service import ProjectService


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


@router.post("/upload", response_model=ProjectDetailResponse)
async def upload_project(
    files: list[UploadFile] = File(...),
    project_name: str | None = Form(default=None),
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.create")),
) -> ProjectDetailResponse:
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
        return await service.create_project(file=None, files=files, requested_name=project_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import-url", response_model=ProjectDetailResponse)
async def import_project_url(
    payload: ImportUrlRequest,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_permission("projects.create")),
) -> ProjectDetailResponse:
    logger.info(
        "project_import_url_requested",
        extra={
            "username": current_user.username,
            "project_name": payload.project_name,
            "url": payload.url,
        },
    )
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
