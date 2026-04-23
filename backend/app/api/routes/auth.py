from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import HTMLResponse

from app.core.auth import require_current_user
from app.schemas.auth import (
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


@router.get("/social-config", response_model=SocialLoginProviderConfigsResponse)
async def social_config(
    current_user: AuthUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
) -> SocialLoginProviderConfigsResponse:
    return SocialLoginProviderConfigsResponse(providers=service.list_social_provider_configs())


@router.put("/social-config/{provider}", response_model=SocialLoginProviderConfig)
async def update_social_config(
    payload: SocialLoginProviderConfigUpdateRequest,
    provider: str = Path(...),
    current_user: AuthUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
) -> SocialLoginProviderConfig:
    updated = service.update_social_provider_config(provider, payload)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provedor social não encontrado.")
    return updated


@router.api_route("/oauth/{provider}/callback", methods=["GET", "POST"], response_class=HTMLResponse)
async def social_oauth_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None) -> HTMLResponse:
    title = f"Callback {provider.title()}"
    if error:
        message = f"O provedor retornou erro: {error}."
        status_label = "Falha"
    elif code:
        message = (
            "O authorization code foi recebido com sucesso. "
            "Esta base já está pronta para armazenar a configuração do provedor, "
            "mas a troca final do code por token e a criação automática da sessão social "
            "ainda dependem da integração server-side específica deste provedor."
        )
        status_label = "Código recebido"
    else:
        message = "O provedor redirecionou para este callback sem code nem erro."
        status_label = "Callback incompleto"

    html = f"""
    <!doctype html>
    <html lang="pt-BR">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{title}</title>
        <style>
          body {{ font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif; background: #f6efe3; color: #0f172a; margin: 0; }}
          main {{ max-width: 760px; margin: 7vh auto; padding: 32px; background: white; border-radius: 28px; box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08); }}
          .kicker {{ text-transform: uppercase; letter-spacing: 0.24em; font-size: 12px; color: #b45309; font-weight: 700; }}
          h1 {{ font-size: 40px; margin: 12px 0 8px; }}
          .status {{ display: inline-block; margin-top: 12px; padding: 8px 14px; border-radius: 999px; background: #fff7ed; color: #9a3412; font-weight: 600; }}
          p, li {{ font-size: 18px; line-height: 1.7; color: #475569; }}
          code {{ background: #f8fafc; padding: 2px 6px; border-radius: 8px; }}
        </style>
      </head>
      <body>
        <main>
          <p class="kicker">Login social</p>
          <h1>{title}</h1>
          <span class="status">{status_label}</span>
          <p>{message}</p>
          <ul>
            <li><strong>Provider:</strong> <code>{provider}</code></li>
            <li><strong>Code:</strong> <code>{code or "não informado"}</code></li>
            <li><strong>State:</strong> <code>{state or "não informado"}</code></li>
          </ul>
          <p>Volte ao SnapMaker3d Studio para continuar a configuração do provedor.</p>
        </main>
      </body>
    </html>
    """
    return HTMLResponse(html, status_code=200 if code and not error else 400)
