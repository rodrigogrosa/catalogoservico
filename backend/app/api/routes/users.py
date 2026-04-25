from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_permission
from app.schemas.auth import (
    AuthUser,
    UserCreateRequest,
    UserListResponse,
    UserRecordResponse,
    UserUpdateRequest,
)
from app.services.user_service import UserService


router = APIRouter()


def get_user_service() -> UserService:
    return UserService()


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: AuthUser = Depends(require_permission("users.view")),
    service: UserService = Depends(get_user_service),
) -> UserListResponse:
    _ = current_user
    return UserListResponse(items=service.list_users())


@router.post("", response_model=UserRecordResponse)
async def create_user(
    payload: UserCreateRequest,
    current_user: AuthUser = Depends(require_permission("users.manage")),
    service: UserService = Depends(get_user_service),
) -> UserRecordResponse:
    _ = current_user
    try:
        return service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{provider}/{username}", response_model=UserRecordResponse)
async def update_user(
    provider: str,
    username: str,
    payload: UserUpdateRequest,
    current_user: AuthUser = Depends(require_permission("users.manage")),
    service: UserService = Depends(get_user_service),
) -> UserRecordResponse:
    _ = current_user
    try:
        updated = service.update_user(username=username, provider=provider, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return updated


@router.delete("/{provider}/{username}")
async def delete_user(
    provider: str,
    username: str,
    current_user: AuthUser = Depends(require_permission("users.manage")),
    service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    if provider == "master" and username == current_user.username:
        raise HTTPException(status_code=409, detail="O usuário master principal não pode ser excluído.")
    if not service.delete_user(username=username, provider=provider):
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"status": "deleted", "provider": provider, "username": username}
