from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_current_user
from app.schemas.auth import AuthUser, LoginRequest, LoginResponse, OAuthProvidersResponse
from app.services.auth_service import AuthService


router = APIRouter()


def get_auth_service() -> AuthService:
    return AuthService()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> LoginResponse:
    result = service.authenticate_master(payload.username, payload.password)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos.")
    return result


@router.get("/me", response_model=AuthUser)
async def me(current_user: AuthUser = Depends(require_current_user)) -> AuthUser:
    return current_user


@router.get("/providers", response_model=OAuthProvidersResponse)
async def providers(service: AuthService = Depends(get_auth_service)) -> OAuthProvidersResponse:
    return OAuthProvidersResponse(providers=service.list_oauth_providers())
