from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_permission
from app.schemas.ai_settings import AiRuntimeSettingsResponse, AiRuntimeSettingsUpdateRequest
from app.schemas.auth import AuthUser
from app.services.ai_settings_service import AiSettingsService


router = APIRouter()


def get_ai_settings_service() -> AiSettingsService:
    return AiSettingsService()


@router.get("", response_model=AiRuntimeSettingsResponse)
async def get_ai_settings(
    current_user: AuthUser = Depends(require_permission("ai_settings.view")),
    service: AiSettingsService = Depends(get_ai_settings_service),
) -> AiRuntimeSettingsResponse:
    _ = current_user
    return service.get_runtime_settings()


@router.put("", response_model=AiRuntimeSettingsResponse)
async def update_ai_settings(
    payload: AiRuntimeSettingsUpdateRequest,
    current_user: AuthUser = Depends(require_permission("ai_settings.manage")),
    service: AiSettingsService = Depends(get_ai_settings_service),
) -> AiRuntimeSettingsResponse:
    _ = current_user
    return service.update_runtime_settings(payload)
