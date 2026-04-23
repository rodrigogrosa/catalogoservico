import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.auth import require_current_user
from app.schemas.auth import AuthUser
from app.schemas.project import (
    ImportUrlRequest,
    ProcessProjectRequest,
    ProjectBundleResponse,
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
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_current_user),
) -> ProjectListResponse:
    logger.info("projects_list_requested", extra={"username": current_user.username})
    return ProjectListResponse(items=service.list_projects())


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_current_user),
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
    current_user: AuthUser = Depends(require_current_user),
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
    current_user: AuthUser = Depends(require_current_user),
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
    current_user: AuthUser = Depends(require_current_user),
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
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_current_user),
) -> ProjectSummary:
    logger.info("project_process_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")

    asyncio.create_task(service.process_project(project_id, payload))
    current = project.model_dump()
    current["status"] = "processing"
    return ProjectSummary(**current)


@router.get("/{project_id}/bundle", response_model=ProjectBundleResponse)
async def build_project_bundle(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_current_user),
) -> ProjectBundleResponse:
    logger.info("project_bundle_requested", extra={"username": current_user.username, "project_id": project_id})
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado.")
    return service.build_bundle(project_id)


@router.get("/{project_id}/compare/{other_project_id}", response_model=ProjectCompareResponse)
async def compare_projects(
    project_id: str,
    other_project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUser = Depends(require_current_user),
) -> ProjectCompareResponse:
    logger.info(
        "project_compare_requested",
        extra={"username": current_user.username, "project_id": project_id, "other_project_id": other_project_id},
    )
    try:
        return service.compare_projects(project_id, other_project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
