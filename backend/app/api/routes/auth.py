from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import get_auth_service, require_current_user, require_permission
from app.schemas.auth import (
    AccessModelResponse,
    AuthUser,
    LoginRequest,
    LoginResponse,
    OAuthProvidersResponse,
    SocialLoginProviderConfig,
    SocialLoginProviderConfigsResponse,
    SocialLoginProviderConfigUpdateRequest,
)
from app.services.auth_service import AuthService


router = APIRouter()


def _make_oauth_state(provider: str, secret: str) -> str:
    """Gera um state HMAC-assinado com timestamp para prevenção de CSRF."""
    ts = str(int(time.time()))
    raw = f"{provider}:{ts}"
    sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{raw}:{sig}"


def _verify_oauth_state(state: str | None, provider: str, secret: str, max_age_seconds: int = 600) -> bool:
    """Valida state HMAC-assinado. Rejeita ausente, malformado, expirado ou com assinatura inválida."""
    if not state:
        return False
    parts = state.split(":")
    if len(parts) != 3:
        return False
    state_provider, ts_str, sig = parts
    if state_provider != provider:
        return False
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if int(time.time()) - ts > max_age_seconds:
        return False
    raw = f"{state_provider}:{ts_str}"
    expected_sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(sig, expected_sig)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> LoginResponse:
    result = service.authenticate_master(payload.username, payload.password)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario ou senha invalidos.")
    return result


@router.get("/me", response_model=AuthUser)
async def me(current_user: AuthUser = Depends(require_current_user)) -> AuthUser:
    return current_user


@router.get("/access-model", response_model=AccessModelResponse)
async def access_model(
    current_user: AuthUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
) -> AccessModelResponse:
    _ = current_user
    return service.access_model()


@router.get("/providers", response_model=OAuthProvidersResponse)
async def providers(service: AuthService = Depends(get_auth_service)) -> OAuthProvidersResponse:
    return OAuthProvidersResponse(providers=service.list_oauth_providers())


@router.get("/social-config", response_model=SocialLoginProviderConfigsResponse)
async def social_config(
    current_user: AuthUser = Depends(require_permission("social_login.manage")),
    service: AuthService = Depends(get_auth_service),
) -> SocialLoginProviderConfigsResponse:
    return SocialLoginProviderConfigsResponse(providers=service.list_social_provider_configs())


@router.put("/social-config/{provider}", response_model=SocialLoginProviderConfig)
async def update_social_config(
    payload: SocialLoginProviderConfigUpdateRequest,
    provider: str = Path(...),
    current_user: AuthUser = Depends(require_permission("social_login.manage")),
    service: AuthService = Depends(get_auth_service),
) -> SocialLoginProviderConfig:
    _ = current_user
    updated = service.update_social_provider_config(provider, payload)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provedor social não encontrado.")
    return updated


@router.api_route("/oauth/{provider}/callback", methods=["GET", "POST"], response_class=HTMLResponse)
async def social_oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    service: AuthService = Depends(get_auth_service),
):
    secret = service.settings.auth_token_secret

    if error:
        html = service.callback_error_html(
            provider,
            "Falha",
            f"O provedor retornou erro: {error}.",
            code=code,
            state=state,
            status_code=400,
        )
        return HTMLResponse(html, status_code=400)

    if not _verify_oauth_state(state, provider, secret):
        html = service.callback_error_html(
            provider,
            "State inválido ou expirado",
            "O parâmetro state ausente, expirado ou inválido. Inicie o fluxo OAuth novamente.",
            code=code,
            state=state,
            status_code=400,
        )
        return HTMLResponse(html, status_code=400)

    if provider == "google" and code:
        try:
            session = service.exchange_google_code(code)
        except ValueError as exc:
            html = service.callback_error_html(
                provider,
                "Falha na troca do código",
                str(exc),
                code=code,
                state=state,
                status_code=400,
            )
            return HTMLResponse(html, status_code=400)
        return RedirectResponse(service.build_social_completion_url(session), status_code=303)

    if code:
        html = service.callback_error_html(
            provider,
            "Integração pendente",
            "O authorization code foi recebido, mas este provedor ainda não teve a troca server-side final implementada nesta base.",
            code=code,
            state=state,
            status_code=200,
        )
        return HTMLResponse(html, status_code=200)

    html = service.callback_error_html(
        provider,
        "Callback incompleto",
        "O provedor redirecionou para este callback sem code nem erro.",
        code=code,
        state=state,
        status_code=400,
    )
    return HTMLResponse(html, status_code=400)

