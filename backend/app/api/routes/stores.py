from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.auth import require_permission
from app.core.config import get_settings
from app.schemas.auth import AuthUser
from app.schemas.store import (
    ConnectorListResponse,
    ProductPublishDraftResponse,
    ProductPublishRequest,
    StoreOAuthAuthorizationResponse,
    StoreCreateRequest,
    StoreListResponse,
    StoreResponse,
    StoreUpdateRequest,
)
from app.services.store_service import StoreService


router = APIRouter()


def get_store_service() -> StoreService:
    return StoreService()


@router.get("/connectors", response_model=ConnectorListResponse)
async def list_connectors(
    current_user: AuthUser = Depends(require_permission("stores.view")),
    service: StoreService = Depends(get_store_service),
) -> ConnectorListResponse:
    _ = current_user
    return ConnectorListResponse(items=service.list_connectors())


@router.get("", response_model=StoreListResponse)
async def list_stores(
    current_user: AuthUser = Depends(require_permission("stores.view")),
    service: StoreService = Depends(get_store_service),
) -> StoreListResponse:
    return StoreListResponse(items=service.list_user_stores(current_user))


@router.post("", response_model=StoreResponse)
async def create_store(
    payload: StoreCreateRequest,
    current_user: AuthUser = Depends(require_permission("stores.manage")),
    service: StoreService = Depends(get_store_service),
) -> StoreResponse:
    return service.create_store(current_user, payload)


@router.put("/{store_id}", response_model=StoreResponse)
async def update_store(
    store_id: str,
    payload: StoreUpdateRequest,
    current_user: AuthUser = Depends(require_permission("stores.manage")),
    service: StoreService = Depends(get_store_service),
) -> StoreResponse:
    store = service.update_store(current_user, store_id, payload)
    if store is None:
        raise HTTPException(status_code=404, detail="Loja nao encontrada.")
    return store


@router.delete("/{store_id}")
async def delete_store(
    store_id: str,
    current_user: AuthUser = Depends(require_permission("stores.manage")),
    service: StoreService = Depends(get_store_service),
) -> dict[str, str]:
    if not service.delete_store(current_user, store_id):
        raise HTTPException(status_code=404, detail="Loja nao encontrada.")
    return {"status": "deleted", "store_id": store_id}


@router.post("/{store_id}/oauth/mercado-livre/start", response_model=StoreOAuthAuthorizationResponse)
async def start_mercado_livre_oauth(
    store_id: str,
    current_user: AuthUser = Depends(require_permission("stores.manage")),
    service: StoreService = Depends(get_store_service),
) -> StoreOAuthAuthorizationResponse:
    try:
        result = service.prepare_mercado_livre_oauth(current_user, store_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Loja nao encontrada.")
    return result


@router.get("/oauth/mercado-livre/callback", response_class=HTMLResponse)
async def mercado_livre_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    service: StoreService = Depends(get_store_service),
) -> HTMLResponse:
    if error:
        return HTMLResponse(
            build_oauth_callback_html("Autorização recusada", f"Mercado Livre retornou erro: {error}", False),
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            build_oauth_callback_html("Callback incompleto", "Mercado Livre não retornou code/state.", False),
            status_code=400,
        )
    try:
        result = service.complete_mercado_livre_oauth(code, state)
    except ValueError as exc:
        return HTMLResponse(build_oauth_callback_html("Falha ao configurar token", str(exc), False), status_code=400)
    return HTMLResponse(
        build_oauth_callback_html(
            "Mercado Livre conectado",
            f"Loja {result.store.name} configurada. Seller ID: {result.seller_id or 'não informado'}. Você já pode voltar ao SnapMaker3d Studio.",
            True,
        )
    )


@router.post("/webhooks/mercado-livre")
async def mercado_livre_notifications(
    request: Request,
    service: StoreService = Depends(get_store_service),
) -> dict[str, str]:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}
    saved = service.record_mercado_livre_notification(
        payload=payload if isinstance(payload, dict) else {"raw": payload},
        headers={key: value for key, value in request.headers.items()},
        query={key: value for key, value in request.query_params.items()},
    )
    return {"status": "received", "path": str(saved)}


@router.post("/{store_id}/publish/{project_id}", response_model=ProductPublishDraftResponse)
async def build_publication_draft(
    store_id: str,
    project_id: str,
    payload: ProductPublishRequest,
    current_user: AuthUser = Depends(require_permission("stores.publish")),
    service: StoreService = Depends(get_store_service),
) -> ProductPublishDraftResponse:
    result = service.build_publication_draft(current_user, store_id, project_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Loja ou projeto nao encontrado.")
    return result


@router.post("/{store_id}/items/{item_id}/refresh-media/{project_id}")
async def refresh_listing_media(
    store_id: str,
    item_id: str,
    project_id: str,
    current_user: AuthUser = Depends(require_permission("stores.publish")),
    service: StoreService = Depends(get_store_service),
) -> dict[str, object]:
    try:
        result = service.refresh_listing_media(current_user, store_id, project_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Loja ou projeto nao encontrado.")
    return result


def build_oauth_callback_html(title: str, message: str, success: bool) -> str:
    color = "#13795b" if success else "#c54237"
    frontend_origin = get_settings().public_frontend_origin.rstrip("/")
    return f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{ margin: 0; font-family: Avenir Next, system-ui, sans-serif; background: #f8f3eb; color: #102033; }}
      main {{ min-height: 100vh; display: grid; place-items: center; padding: 32px; }}
      section {{ max-width: 720px; border-top: 6px solid {color}; background: white; padding: 36px; box-shadow: 0 24px 80px rgba(16,32,51,.12); }}
      h1 {{ margin: 0 0 16px; font-size: 36px; line-height: 1.1; }}
      p {{ font-size: 18px; line-height: 1.7; }}
      a {{ display: inline-flex; margin-top: 20px; padding: 14px 22px; border-radius: 999px; background: #102033; color: white; text-decoration: none; font-weight: 700; }}
    </style>
  </head>
  <body>
    <main>
      <section>
        <h1>{title}</h1>
        <p>{message}</p>
        <a href="{frontend_origin}/stores">Voltar para Lojas</a>
      </section>
    </main>
  </body>
</html>"""
