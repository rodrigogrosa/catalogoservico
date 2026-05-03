from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import mimetypes
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)
import secrets
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.auth import AuthUser
from app.schemas.store import (
    ConnectorCapability,
    ConnectorField,
    MarketplaceConnector,
    ProductPublishDraftResponse,
    ProductPublishRequest,
    StoreCreateRequest,
    StoreOAuthAuthorizationResponse,
    StoreOAuthCallbackResponse,
    StoreCredentialStatus,
    StoreResponse,
    StoreUpdateRequest,
)
from app.services.project_service import ProjectService
from app.services.storage_service import StorageService


class StoreService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = StorageService()
        self.data_dir = self.settings.storage_root / "_system"
        self.data_path = self.data_dir / "stores.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def list_connectors(self) -> list[MarketplaceConnector]:
        return [
            MarketplaceConnector(
                marketplace="mercado_livre",
                label="Mercado Livre",
                docs_url="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization",
                auth_type="OAuth 2.0 Bearer token",
                required_credentials=[
                    ConnectorField(
                        key="client_id",
                        label="APP ID / Client ID",
                        secret=False,
                        group="1. Aplicação no Mercado Livre",
                        help_text="É o ID do aplicativo exibido em DevCenter > Minhas aplicações > Configurar. Na API também aparece como client_id.",
                        help_url="https://developers.mercadolivre.com.br/en_us/products-authentication-authorization/register-your-application",
                    ),
                    ConnectorField(
                        key="client_secret",
                        label="Chave secreta / Client Secret",
                        secret=True,
                        group="1. Aplicação no Mercado Livre",
                        help_text="É a chave secreta do aplicativo. Não compartilhe fora deste ambiente local.",
                        help_url="https://developers.mercadolivre.com.br/en_us/products-authentication-authorization/register-your-application",
                    ),
                    ConnectorField(
                        key="redirect_uri",
                        label="Redirect URI cadastrada",
                        secret=False,
                        group="1. Aplicação no Mercado Livre",
                        help_text="Deve ser exatamente a mesma URL cadastrada no app. O Mercado Livre exige correspondência exata para gerar token.",
                        help_url="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization",
                    ),
                    ConnectorField(
                        key="authorization_code",
                        label="Código de autorização",
                        secret=True,
                        required=False,
                        group="2. Autorização OAuth",
                        help_text="Código temporário recebido na Redirect URI depois de autorizar a aplicação. Serve para trocar por access_token.",
                        help_url="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization",
                    ),
                    ConnectorField(
                        key="access_token",
                        label="Access Token do vendedor",
                        secret=True,
                        required=False,
                        group="2. Autorização OAuth",
                        help_text="Token Bearer usado nas chamadas privadas. Obrigatório para publicação automática real.",
                        help_url="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization",
                    ),
                    ConnectorField(
                        key="refresh_token",
                        label="Refresh Token",
                        secret=True,
                        required=False,
                        group="2. Autorização OAuth",
                        help_text="Token usado para renovar o access_token. Ele muda a cada renovação e só o último é válido.",
                        help_url="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization",
                    ),
                    ConnectorField(
                        key="seller_id",
                        label="Seller ID / User ID",
                        secret=False,
                        required=False,
                        group="3. Conta vendedora",
                        help_text="ID da conta vendedora retornado como user_id no OAuth ou via /users/me usando o access_token.",
                        help_url="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization",
                    ),
                ],
                required_product_fields=[
                    "title",
                    "category_id",
                    "price",
                    "currency_id",
                    "available_quantity",
                    "buying_mode",
                    "condition",
                    "listing_type_id",
                    "pictures",
                ],
                capabilities=[
                    ConnectorCapability(key="draft_payload", label="Gerar payload de anúncio", implemented=True),
                    ConnectorCapability(key="publish_item", label="Publicar item automaticamente", implemented=False, notes="Requer OAuth completo, categoria válida e imagens hospedadas."),
                    ConnectorCapability(key="upload_pictures", label="Enviar imagens", implemented=False, notes="Preparado como próximo adaptador."),
                ],
                implementation_notes=[
                    "Para configurar o aplicativo, preencha APP ID, Client Secret e Redirect URI.",
                    "Para publicar de fato, autorize a conta vendedora e obtenha access_token/refresh_token via OAuth.",
                    "A publicação real deve validar categoria, atributos obrigatórios e imagem antes do POST final.",
                    "O sistema gera payload compatível e bloqueia publish enquanto credenciais, categoria ou imagens públicas estiverem ausentes.",
                ],
            ),
            MarketplaceConnector(
                marketplace="shopee",
                label="Shopee",
                docs_url="https://open.shopee.com/documents/v2/v2.product.add_item?module=89&type=1",
                auth_type="Open Platform partner_id + shop_id + signed requests",
                required_credentials=[
                    ConnectorField(key="partner_id", label="Partner ID", secret=False),
                    ConnectorField(key="partner_key", label="Partner Key", secret=True),
                    ConnectorField(key="shop_id", label="Shop ID", secret=False),
                    ConnectorField(key="access_token", label="Access Token", secret=True),
                ],
                required_product_fields=[
                    "item_name",
                    "description",
                    "category_id",
                    "price_info",
                    "stock_info",
                    "image",
                    "logistic_info",
                    "weight",
                    "dimension",
                ],
                capabilities=[
                    ConnectorCapability(key="draft_payload", label="Gerar payload de anúncio", implemented=True),
                    ConnectorCapability(key="publish_item", label="Criar produto via add_item", implemented=False, notes="Requer assinatura HMAC e categoria/logística reais."),
                    ConnectorCapability(key="upload_image", label="Enviar imagem", implemented=False),
                ],
                implementation_notes=[
                    "Shopee exige categoria, logística, peso/dimensões e assinatura de cada chamada.",
                    "O adaptador inicial gera payload e checklist para evitar publicação incompleta.",
                ],
            ),
            MarketplaceConnector(
                marketplace="meta_instagram",
                label="Instagram / Meta Catalog",
                docs_url="https://developers.facebook.com/docs/marketing-api/catalog-batch/guides/send-item-updates/",
                auth_type="Meta OAuth token com catalog_management/business_management",
                required_credentials=[
                    ConnectorField(key="business_id", label="Business ID", secret=False),
                    ConnectorField(key="catalog_id", label="Catalog ID", secret=False),
                    ConnectorField(key="access_token", label="Access Token", secret=True),
                ],
                required_product_fields=[
                    "id",
                    "title",
                    "description",
                    "availability",
                    "condition",
                    "price",
                    "link",
                    "image_link",
                    "brand",
                ],
                capabilities=[
                    ConnectorCapability(key="draft_payload", label="Gerar item de catálogo", implemented=True),
                    ConnectorCapability(key="catalog_batch", label="Enviar lote para catálogo", implemented=False, notes="Requer catálogo, token e URL pública de imagem/produto."),
                    ConnectorCapability(key="csv_feed", label="Gerar feed CSV", implemented=True),
                ],
                implementation_notes=[
                    "Instagram Shopping depende de conta profissional, Business Manager e catálogo aprovado.",
                    "A publicação via feed exige URLs públicas para página do produto e imagem principal.",
                ],
            ),
            MarketplaceConnector(
                marketplace="custom_store",
                label="Loja própria / Genérica",
                docs_url="",
                auth_type="Webhook/API própria",
                required_credentials=[
                    ConnectorField(key="endpoint_url", label="Endpoint de publicação", secret=False),
                    ConnectorField(key="api_key", label="API Key", secret=True, required=False),
                ],
                required_product_fields=["title", "description", "price", "images", "files"],
                capabilities=[
                    ConnectorCapability(key="draft_payload", label="Gerar payload genérico", implemented=True),
                    ConnectorCapability(key="publish_item", label="Publicar via webhook", implemented=False, notes="Depende do contrato da loja."),
                ],
                implementation_notes=["Use para Shopify/WooCommerce/custom enquanto o conector específico não existir."],
            ),
        ]

    def list_user_stores(self, user: AuthUser) -> list[StoreResponse]:
        stores = [item for item in self.load_store_records() if item.get("owner_username") == user.username]
        stores.sort(key=self.store_priority_score, reverse=True)
        return [self.to_response(record) for record in stores]

    def create_store(self, user: AuthUser, payload: StoreCreateRequest) -> StoreResponse:
        connector = self.get_connector(payload.marketplace)
        now = datetime.now(tz=timezone.utc).isoformat()
        record = {
            "id": uuid4().hex,
            "owner_username": user.username,
            "name": payload.name.strip(),
            "marketplace": payload.marketplace,
            "account_label": payload.account_label,
            "country": payload.country,
            "currency": payload.currency,
            "status": self.infer_status(connector, payload.credentials),
            "credentials": self.sanitize_credentials(payload.credentials),
            "settings": payload.settings,
            "created_at": now,
            "updated_at": now,
        }
        records = self.load_store_records()
        records.append(record)
        self.write_store_records(records)
        return self.to_response(record)

    def update_store(self, user: AuthUser, store_id: str, payload: StoreUpdateRequest) -> StoreResponse | None:
        records = self.load_store_records()
        for record in records:
            if record.get("id") != store_id or record.get("owner_username") != user.username:
                continue
            connector = self.get_connector(record["marketplace"])
            if payload.name is not None:
                record["name"] = payload.name.strip()
            if payload.account_label is not None:
                record["account_label"] = payload.account_label
            if payload.country is not None:
                record["country"] = payload.country
            if payload.currency is not None:
                record["currency"] = payload.currency
            if payload.settings:
                record["settings"] = {**record.get("settings", {}), **payload.settings}
            if payload.credentials:
                record["credentials"] = {**record.get("credentials", {}), **self.sanitize_credentials(payload.credentials)}
            record["status"] = payload.status or self.infer_status(connector, record.get("credentials", {}))
            record["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            self.write_store_records(records)
            return self.to_response(record)
        return None

    def delete_store(self, user: AuthUser, store_id: str) -> bool:
        records = self.load_store_records()
        kept = [record for record in records if not (record.get("id") == store_id and record.get("owner_username") == user.username)]
        if len(kept) == len(records):
            return False
        self.write_store_records(kept)
        return True

    def default_mercado_livre_redirect_uri(self) -> str:
        return f"{self.settings.public_backend_origin.rstrip('/')}/api/v1/stores/oauth/mercado-livre/callback"

    def default_mercado_livre_notifications_url(self) -> str:
        return f"{self.settings.public_backend_origin.rstrip('/')}/api/v1/stores/webhooks/mercado-livre"

    def prepare_mercado_livre_oauth(self, user: AuthUser, store_id: str) -> StoreOAuthAuthorizationResponse | None:
        records = self.load_store_records()
        for record in records:
            if record.get("id") != store_id or record.get("owner_username") != user.username:
                continue
            if record.get("marketplace") != "mercado_livre":
                raise ValueError("OAuth automático disponível apenas para Mercado Livre.")
            credentials = record.setdefault("credentials", {})
            client_id = credentials.get("client_id", "").strip()
            client_secret = credentials.get("client_secret", "").strip()
            if not client_id or not client_secret:
                raise ValueError("Configure APP ID e chave secreta antes de iniciar OAuth.")
            current_redirect_uri = credentials.get("redirect_uri", "").strip()
            redirect_uri = (
                self.default_mercado_livre_redirect_uri()
                if not current_redirect_uri or current_redirect_uri.startswith("http://")
                else current_redirect_uri
            )
            credentials["redirect_uri"] = redirect_uri
            state = secrets.token_urlsafe(24)
            settings = record.setdefault("settings", {})
            settings["mercado_livre_oauth_state"] = state
            settings["mercado_livre_redirect_uri_to_register"] = redirect_uri
            settings["mercado_livre_notifications_url"] = settings.get("mercado_livre_notifications_url") or self.default_mercado_livre_notifications_url()
            settings["mercado_livre_oauth_started_at"] = datetime.now(tz=timezone.utc).isoformat()
            record["status"] = self.infer_status(self.get_connector("mercado_livre"), credentials)
            record["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            self.write_store_records(records)
            query = urlencode(
                {
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "state": state,
                }
            )
            return StoreOAuthAuthorizationResponse(
                store=self.to_response(record),
                authorization_url=f"https://auth.mercadolivre.com.br/authorization?{query}",
                redirect_uri=redirect_uri,
                state=state,
                instructions=[
                    "Cadastre a Redirect URI exatamente igual no DevCenter do Mercado Livre antes de autorizar.",
                    "Abra a URL de autorização e faça login com a conta vendedora principal, não com operador.",
                    "Ao voltar para o callback local, o sistema troca o código por access_token e refresh_token automaticamente.",
                ],
            )
        return None

    def complete_mercado_livre_oauth(self, code: str, state: str) -> StoreOAuthCallbackResponse:
        records = self.load_store_records()
        for record in records:
            settings = record.get("settings", {})
            if record.get("marketplace") != "mercado_livre" or settings.get("mercado_livre_oauth_state") != state:
                continue
            credentials = record.setdefault("credentials", {})
            token_payload = self.exchange_mercado_livre_code(
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", ""),
                code=code,
                redirect_uri=credentials.get("redirect_uri", "") or self.default_mercado_livre_redirect_uri(),
            )
            credentials["authorization_code"] = code
            credentials["access_token"] = str(token_payload.get("access_token", ""))
            credentials["refresh_token"] = str(token_payload.get("refresh_token", ""))
            credentials["seller_id"] = str(token_payload.get("user_id", ""))
            settings["mercado_livre_oauth_completed_at"] = datetime.now(tz=timezone.utc).isoformat()
            settings["mercado_livre_token_type"] = token_payload.get("token_type")
            settings["mercado_livre_token_expires_in"] = token_payload.get("expires_in")
            settings.pop("mercado_livre_oauth_state", None)
            record["status"] = self.infer_status(self.get_connector("mercado_livre"), credentials)
            record["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            self.write_store_records(records)
            return StoreOAuthCallbackResponse(
                store=self.to_response(record),
                status="oauth_configured",
                seller_id=credentials.get("seller_id"),
                expires_in=int(token_payload["expires_in"]) if token_payload.get("expires_in") else None,
            )
        raise ValueError("Estado OAuth inválido ou expirado. Gere uma nova URL de autorização na tela de Lojas.")

    def record_mercado_livre_notification(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        query: dict[str, str],
    ) -> Path:
        notifications_dir = self.data_dir / "mercado_livre_notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = notifications_dir / f"{timestamp}.json"
        path.write_text(
            json.dumps(
                {
                    "received_at": datetime.now(tz=timezone.utc).isoformat(),
                    "headers": headers,
                    "query": query,
                    "payload": payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def exchange_mercado_livre_code(self, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
        if not client_id or not client_secret or not code or not redirect_uri:
            raise ValueError("OAuth Mercado Livre incompleto: client_id, client_secret, code e redirect_uri são obrigatórios.")
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        ).encode("utf-8")
        request = Request(
            "https://api.mercadolibre.com/oauth/token",
            data=body,
            method="POST",
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - official OAuth endpoint.
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Falha ao trocar código por token no Mercado Livre: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValueError(f"Falha de rede no OAuth Mercado Livre: {exc.reason}") from exc

    def build_publication_draft(
        self,
        user: AuthUser,
        store_id: str,
        project_id: str,
        payload: ProductPublishRequest,
    ) -> ProductPublishDraftResponse | None:
        store = next((item for item in self.load_store_records() if item.get("id") == store_id and item.get("owner_username") == user.username), None)
        if store is None:
            return None
        project = ProjectService().get_project(project_id)
        if project is None:
            return None

        connector = self.get_connector(store["marketplace"])
        product_payload = self.build_payload_for_marketplace(connector, store, project.model_dump(), payload)
        credential_blockers = self.missing_required_credentials(connector, store.get("credentials", {}))
        blockers = [*credential_blockers, *self.marketplace_publish_blockers(connector, store, product_payload)]
        if not product_payload.get("images") and not self.can_upload_images_during_publish(connector, store, project.model_dump(), payload):
            blockers.append("Nenhuma imagem pública foi encontrada. Gere/baixe imagens ou configure image_base_url.")

        if payload.mode == "publish" and not blockers:
            try:
                publication_result = self.publish_product(connector, store, product_payload, project.model_dump())
            except ValueError as exc:
                message = str(exc)
                if connector.marketplace == "mercado_livre" and "invalid access token" in message.lower():
                    self.invalidate_store_token(store["id"], {"access_token", "refresh_token", "authorization_code"})
                    blockers.append("Mercado Livre: access_token expirado ou inválido. Autorize a loja novamente para publicar.")
                else:
                    blockers.append(message)
            else:
                return ProductPublishDraftResponse(
                    status="published",
                    store_id=store["id"],
                    store_name=store["name"],
                    marketplace=store["marketplace"],
                    project_id=project_id,
                    can_publish=True,
                    blockers=[],
                    warnings=[
                        "Revise regras de propriedade intelectual antes de publicar personagens/licenciados.",
                        "Confirme prazo de produção e estoque antes de ativar anúncio.",
                    ],
                    payload=product_payload,
                    next_steps=["Anúncio publicado. Revise título, fotos e atributos diretamente no marketplace."],
                    published_item_id=str(publication_result.get("id", "")) or None,
                    published_permalink=publication_result.get("permalink"),
                    publication_reference=publication_result,
                )

        return ProductPublishDraftResponse(
            status="blocked" if blockers else "draft_ready",
            store_id=store["id"],
            store_name=store["name"],
            marketplace=store["marketplace"],
            project_id=project_id,
            can_publish=not blockers,
            blockers=blockers,
            warnings=[
                "Revise regras de propriedade intelectual antes de publicar personagens/licenciados.",
                "Confirme prazo de produção e estoque antes de ativar anúncio.",
            ],
            payload=product_payload,
            next_steps=self.next_steps(connector, blockers),
        )

    def refresh_listing_media(
        self,
        user: AuthUser,
        store_id: str,
        project_id: str,
        item_id: str,
    ) -> dict[str, Any] | None:
        store = next((item for item in self.load_store_records() if item.get("id") == store_id and item.get("owner_username") == user.username), None)
        if store is None:
            return None
        project = ProjectService().get_project(project_id)
        if project is None:
            return None

        connector = self.get_connector(store["marketplace"])
        if connector.marketplace != "mercado_livre":
            raise ValueError("Atualização de fotos publicada só está implementada para Mercado Livre.")

        product_payload = self.build_payload_for_marketplace(
            connector,
            store,
            project.model_dump(),
            ProductPublishRequest(mode="draft", stock=1),
        )
        pictures = list(product_payload.get("pictures") or [])
        if not pictures:
            raise ValueError("Nenhuma imagem tratada foi encontrada para atualizar o anúncio.")

        access_token = str(store.get("credentials", {}).get("access_token", "")).strip()
        if not access_token:
            raise ValueError("Mercado Livre: access_token ausente para atualização de fotos.")

        updated = self.mercado_livre_api_request(
            access_token=access_token,
            method="PUT",
            path=f"/items/{item_id}",
            payload={"pictures": pictures},
        )
        return {
            "status": "updated",
            "item_id": item_id,
            "permalink": updated.get("permalink"),
            "pictures_count": len(pictures),
            "pictures": pictures,
            "reference": updated,
        }

    def build_payload_for_marketplace(
        self,
        connector: MarketplaceConnector,
        store: dict[str, Any],
        project: dict[str, Any],
        request: ProductPublishRequest,
    ) -> dict[str, Any]:
        sales = project.get("sales_profile") or {}
        channels = sales.get("marketplace_attributes") or []
        channel = next((item for item in channels if self.matches_channel(connector.marketplace, item.get("marketplace", ""))), channels[0] if channels else {})
        price = float(request.price_override_brl or sales.get("suggested_price_50_margin_brl") or 0)
        price = max(price, 80.0)  # preço mínimo R$80,00 por política comercial
        images = self.resolve_product_images(project, request.image_base_url, store)
        # Always derive title from current project name — the saved channel.title may be stale
        # (generated when the project had no name yet). channel.title is only used as last resort.
        _proj_name = str(project.get("name") or "").strip()
        _proj_slug = _proj_name.replace("_", " ").replace("-", " ").strip().title()
        title = _proj_slug or str(channel.get("title") or "Produto impresso em 3D")
        description = str(channel.get("full_description") or channel.get("description") or "Produto impresso em 3D sob demanda.")

        if connector.marketplace == "mercado_livre":
            stored_category_id = str(store.get("settings", {}).get("category_id", "")).strip()
            category_id = stored_category_id if self.looks_like_mercado_livre_category_id(stored_category_id) else self.predict_mercado_livre_category_id(store, project, title, channel)
            images = self.limit_mercado_livre_images(category_id, images)
            ml_title = self._truncate_ml_title(title)
            variations_data = list(sales.get("variations") or [])
            if variations_data:
                ml_variations = [
                    {
                        "price": round(float(v.get("price_brl", price)), 2),
                        "available_quantity": int(v.get("stock", request.stock)),
                        "seller_custom_field": str(v.get("sku", "")),
                        "attribute_combinations": [
                            {"id": "COLOR", "value_name": str(v.get("name", "Padrão"))}
                        ],
                    }
                    for v in variations_data
                ]
            else:
                ml_variations = []
            # Build warranty sale_terms from sales_profile
            warranty_data = sales.get("warranty") or {}
            _wtype = str(warranty_data.get("type") or "seller")
            _wduration = int(warranty_data.get("duration") or 1)
            _wunit = str(warranty_data.get("unit") or "months")
            _wunit_label = "meses" if _wunit in ("months", "meses") else "anos"
            _wtype_label = "Garantia do vendedor" if _wtype == "seller" else "Sem garantia"
            ml_sale_terms = [
                {"id": "WARRANTY_TYPE", "value_name": _wtype_label},
                {"id": "WARRANTY_TIME", "value_name": f"{_wduration} {_wunit_label}"},
            ]
            payload: dict[str, Any] = {
                "title": ml_title,
                "category_id": category_id,
                "price": round(price, 2),
                "available_quantity": request.stock,
                "currency_id": "BRL",
                "buying_mode": "buy_it_now",
                "condition": "new",
                "listing_type_id": store.get("settings", {}).get("listing_type_id", "gold_special"),
                "pictures": [{"source": image} for image in images],
                "sale_terms": ml_sale_terms,
                "description_plain_text": description,
                "attributes": self.build_mercado_livre_attributes(category_id, project, channel),
                "images": images,
                "category_prediction_applied": bool(category_id) and not self.looks_like_mercado_livre_category_id(stored_category_id),
            }
            if ml_variations:
                payload["variations"] = ml_variations
                # ML rule: any attribute ID used in variation.attribute_combinations
                # MUST NOT also appear in item.attributes — causes error item.attributes.invalid.
                variation_combo_ids: set[str] = set()
                for var in ml_variations:
                    for combo in var.get("attribute_combinations") or []:
                        if combo.get("id"):
                            variation_combo_ids.add(str(combo["id"]))
                if variation_combo_ids:
                    payload["attributes"] = [
                        attr for attr in payload["attributes"]
                        if attr.get("id") not in variation_combo_ids
                    ]
            return payload
        if connector.marketplace == "shopee":
            return {
                "item_name": title[:120],
                "description": description,
                "category_id": store.get("settings", {}).get("category_id", ""),
                "price_info": [{"original_price": round(price, 2)}],
                "stock_info": [{"stock_type": 2, "current_stock": request.stock}],
                "image": {"image_url_list": images},
                "weight": store.get("settings", {}).get("weight_kg", 0.1),
                "dimension": store.get("settings", {}).get("dimension_cm", {"package_length": 15, "package_width": 15, "package_height": 8}),
                "logistic_info": store.get("settings", {}).get("logistic_info", []),
                "images": images,
            }
        if connector.marketplace == "meta_instagram":
            product_url = request.product_url or store.get("settings", {}).get("default_product_url", "")
            return {
                "id": project.get("id"),
                "title": title[:200],
                "description": description,
                "availability": "in stock",
                "condition": "new",
                "price": f"{round(price, 2)} BRL",
                "link": product_url,
                "image_link": images[0] if images else "",
                "brand": store.get("settings", {}).get("brand", "SnapMaker3d Studio"),
                "inventory": request.stock,
                "images": images,
            }
        return {
            "title": title,
            "description": description,
            "price": round(price, 2),
            "currency": store.get("currency", "BRL"),
            "stock": request.stock,
            "images": images,
            "project_id": project.get("id"),
            "download_bundle": next((item.get("path") for item in project.get("bundles", []) if item.get("path")), None),
        }

    def resolve_product_images(self, project: dict[str, Any], image_base_url: str | None, store: dict[str, Any] | None = None) -> list[str]:
        sales = project.get("sales_profile") or {}
        hidden_set = set(sales.get("hidden_photo_paths") or [])
        extra_photos = list(sales.get("extra_ad_photos") or [])

        photo_order: list[str] = list(sales.get("photo_order") or [])

        previews = list(project.get("previews", []) or [])
        # Use all previews — marketplace_preview filtering was too restrictive and excluded real photos
        raw_paths = [project.get("preview_url")] + [item.get("path") for item in previews]
        candidate_bases = self.image_base_url_candidates(image_base_url, store)
        primary_base = candidate_bases[0] if candidate_bases else self.settings.public_backend_origin.rstrip("/")
        public_paths: list[str] = []
        for raw_path in raw_paths:
            if not raw_path:
                continue
            path = str(raw_path)
            if not path.lower().split("?")[0].endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            if path.startswith("http"):
                full_url = path
                if full_url in hidden_set:
                    continue
                if self.is_public_http_image(full_url):
                    public_paths.append(full_url)
                continue
            full_url = f"{primary_base}{path}"
            if full_url in hidden_set or path in hidden_set:
                continue
            public_paths.append(full_url)
        # Append user-added extra photos
        for ep in extra_photos:
            ep_path = str(ep.get("path") if isinstance(ep, dict) else getattr(ep, "path", ""))
            if not ep_path or ep_path in hidden_set:
                continue
            if not ep_path.lower().split("?")[0].endswith((".png", ".jpg", ".jpeg", ".webp")):
                ep_path = ep_path  # include anyway — ML will validate
            public_paths.append(ep_path)
        deduped = list(dict.fromkeys(public_paths))
        # Apply explicit photo_order from sales_profile (user-defined ordering)
        if photo_order:
            order_index = {url: i for i, url in enumerate(photo_order)}
            in_order = [u for u in photo_order if u in set(deduped)]
            rest = [u for u in deduped if u not in order_index]
            deduped = in_order + rest
        return deduped

    def resolve_local_product_images(self, project: dict[str, Any]) -> list[str]:
        """Return absolute filesystem paths to preview images stored locally.

        Preview paths are stored as URL-relative strings like ``/storage/projects/abc/photo.jpg``.
        They must be resolved against ``settings.storage_root`` to get the actual filesystem path
        (e.g. ``{storage_root}/projects/abc/photo.jpg``).  Using the URL path directly in
        ``Path(...).exists()`` always returns False in production, which is the root cause of the
        fallback-to-URL-download path being triggered every time.
        """
        storage_root = self.settings.storage_root
        previews = list(project.get("previews", []) or [])
        marketplace_paths = [
            item.get("path")
            for item in previews
            if str(item.get("kind", "")).lower() == "marketplace_preview"
            or "marketplace_" in str(item.get("label", "")).lower()
            or "marketplace_" in str(item.get("path", "")).lower()
        ]
        candidate_paths = marketplace_paths or [item.get("path") for item in previews]
        local_paths: list[str] = []
        for candidate in candidate_paths:
            if not candidate:
                continue
            candidate_str = str(candidate)
            # Resolve URL-relative paths like /storage/... against the filesystem storage root.
            if candidate_str.startswith("/storage/"):
                fs_path = storage_root / candidate_str[len("/storage/"):]
            else:
                fs_path = Path(candidate_str)
            if fs_path.exists() and fs_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                local_paths.append(str(fs_path))
        return list(dict.fromkeys(local_paths))

    def image_base_url_candidates(self, request_image_base_url: str | None, store: dict[str, Any] | None) -> list[str]:
        candidates: list[str] = []
        if request_image_base_url:
            candidates.append(request_image_base_url.rstrip("/"))
        store_settings = store.get("settings", {}) if store else {}
        if isinstance(store_settings.get("image_base_url"), str) and store_settings.get("image_base_url"):
            candidates.append(str(store_settings["image_base_url"]).rstrip("/"))
        if self.settings.public_backend_origin.startswith("https://"):
            candidates.append(self.settings.public_backend_origin.rstrip("/"))
        candidates.append("https://api.euachei3d.com.br")
        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    def is_public_http_image(self, url: str) -> bool:
        lowered = url.lower()
        blocked_hosts = ("127.0.0.1", "localhost", "0.0.0.0")
        return not any(host in lowered for host in blocked_hosts)

    def next_steps(self, connector: MarketplaceConnector, blockers: list[str]) -> list[str]:
        steps = ["Revise o payload gerado na tela antes de publicar."]
        if blockers:
            steps.append("Resolva os bloqueios listados antes de ativar publicação automática.")
        steps.extend(connector.implementation_notes)
        return steps

    def publish_product(
        self,
        connector: MarketplaceConnector,
        store: dict[str, Any],
        product_payload: dict[str, Any],
        project: dict[str, Any],
    ) -> dict[str, Any]:
        if connector.marketplace == "mercado_livre":
            return self.publish_mercado_livre_item(store, product_payload, project)
        raise ValueError(f"Publicação automática ainda não implementada para {connector.marketplace}.")

    def publish_mercado_livre_item(self, store: dict[str, Any], product_payload: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
        access_token = str(store.get("credentials", {}).get("access_token", "")).strip()
        if not access_token:
            raise ValueError("Mercado Livre: access_token ausente para publicação.")

        # Always prefer local file upload to ML — source URLs from our backend aren't
        # publicly downloadable by ML's servers. Only fall back to source URLs if no
        # local files exist.
        local_images = self.resolve_local_product_images(project)
        if local_images:
            product_payload["pictures"] = self.upload_local_mercado_livre_pictures(access_token, local_images)
        elif not product_payload.get("pictures"):
            pass  # no pictures available at all
        else:
            # Pictures exist only as source URLs (not yet uploaded to ML).
            # Download each URL to a temp file and upload so ML gets proper picture IDs.
            source_urls = [
                p["source"]
                for p in product_payload["pictures"]
                if p.get("source") and not p.get("id")
            ]
            if source_urls:
                uploaded_from_urls = self._upload_pictures_from_urls(access_token, source_urls)
                if uploaded_from_urls:
                    product_payload["pictures"] = uploaded_from_urls

        # ML requires every variation to have picture_ids when pictures are present.
        # Assign all uploaded picture IDs to each variation.
        uploaded_pictures: list[dict[str, str]] = list(product_payload.get("pictures") or [])
        picture_ids = [p["id"] for p in uploaded_pictures if p.get("id")]
        if product_payload.get("variations"):
            if not picture_ids:
                raise ValueError(
                    "Mercado Livre: não foi possível carregar imagens para atribuir às variações. "
                    "Adicione imagens de preview ao projeto antes de publicar. "
                    "(Dica: gere previews na aba de pré-visualização do projeto.)"
                )
            product_payload["variations"] = [
                {**v, "picture_ids": picture_ids}
                for v in product_payload["variations"]
            ]

        item_payload = {
            key: value
            for key, value in product_payload.items()
            if key in {"title", "category_id", "price", "currency_id", "available_quantity", "buying_mode", "condition", "listing_type_id", "pictures", "attributes", "variations", "sale_terms"}
        }
        # Fall back to store-level sale_terms only if not already built from the project
        if not item_payload.get("sale_terms"):
            item_payload["sale_terms"] = store.get("settings", {}).get("sale_terms", [])

        self.mercado_livre_validate_item(access_token, item_payload)

        created = self.mercado_livre_api_request(
            access_token=access_token,
            method="POST",
            path="/items",
            payload=item_payload,
        )
        item_id = str(created.get("id", "")).strip()
        description_plain_text = str(product_payload.get("description_plain_text", "")).strip()
        if item_id and description_plain_text:
            try:
                self.mercado_livre_api_request(
                    access_token=access_token,
                    method="POST",
                    path=f"/items/{item_id}/description",
                    payload={"plain_text": description_plain_text},
                )
            except Exception:  # noqa: BLE001
                pass  # description is optional; do not fail the whole publish
        return created

    def upload_local_mercado_livre_pictures(self, access_token: str, image_paths: list[str]) -> list[dict[str, str]]:
        uploaded: list[dict[str, str]] = []
        for image_path in image_paths[:8]:
            uploaded.append(self.mercado_livre_upload_picture(access_token, image_path))
        return uploaded

    def _upload_pictures_from_urls(self, access_token: str, source_urls: list[str]) -> list[dict[str, str]]:
        """Download source-URL images to temp files and upload them to Mercado Livre.

        Used as a fallback when no local preview files are available but the payload
        already contains public source URLs (e.g. from the project's previews served
        by this backend).  ML cannot fetch our backend URLs directly, so we download
        each image ourselves and re-upload it via the ML picture upload endpoint.
        """
        uploaded: list[dict[str, str]] = []
        errors: list[str] = []
        for url in source_urls[:8]:
            try:
                req = Request(url, headers={"User-Agent": "SnapMaker3dStudio/1.0"})
                with urlopen(req, timeout=30) as resp:  # noqa: S310
                    data = resp.read()
                raw_path = url.split("?")[0]
                suffix = Path(raw_path).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                    suffix = ".jpg"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name
                try:
                    uploaded.append(self.mercado_livre_upload_picture(access_token, tmp_path))
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
        if errors:
            logger.warning(
                "ML picture upload from source URLs: %d/%d failed. Errors: %s",
                len(errors),
                len(source_urls),
                "; ".join(errors[:3]),
            )
        return uploaded

    def mercado_livre_upload_picture(self, access_token: str, image_path: str) -> dict[str, str]:
        path = Path(image_path)
        if not path.exists():
            raise ValueError(f"Arquivo de preview não encontrado para upload: {path}")
        boundary = f"----SnapMaker3dStudio{uuid4().hex}"
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        file_bytes = path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8"),
                f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        request = Request(
            "https://api.mercadolibre.com/pictures/items/upload",
            data=body,
            method="POST",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {access_token}",
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Falha ao subir preview para o Mercado Livre: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValueError(f"Falha de rede ao subir preview para o Mercado Livre: {exc.reason}") from exc

        picture_id = str(payload.get("id", "")).strip()
        if not picture_id:
            raise ValueError("Mercado Livre não retornou id da imagem enviada.")
        return {"id": picture_id}

    def mercado_livre_validate_item(self, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            "https://api.mercadolibre.com/items/validate",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Bearer {access_token}",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            parsed = self.parse_mercado_livre_error_payload(detail)
            if self.is_warning_only_mercado_livre_validation_error(parsed):
                return parsed
            raise ValueError(f"Mercado Livre API /items/validate falhou: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValueError(f"Falha de rede ao publicar no Mercado Livre: {exc.reason}") from exc

    def parse_mercado_livre_error_payload(self, detail: str) -> dict[str, Any]:
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def is_warning_only_mercado_livre_validation_error(self, payload: dict[str, Any]) -> bool:
        if payload.get("error") != "validation_error":
            return False
        causes = payload.get("cause")
        if not isinstance(causes, list) or not causes:
            return False
        return all(isinstance(cause, dict) and str(cause.get("type", "")).lower() == "warning" for cause in causes)

    def mercado_livre_api_request(
        self,
        *,
        access_token: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"https://api.mercadolibre.com{path}",
            data=data,
            method=method,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Bearer {access_token}",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Mercado Livre API {path} falhou: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValueError(f"Falha de rede ao publicar no Mercado Livre: {exc.reason}") from exc

    def marketplace_publish_blockers(
        self,
        connector: MarketplaceConnector,
        store: dict[str, Any],
        product_payload: dict[str, Any],
    ) -> list[str]:
        credentials = store.get("credentials", {})
        blockers: list[str] = []
        if connector.marketplace == "mercado_livre":
            if not credentials.get("access_token"):
                blockers.append("Mercado Livre: access_token do vendedor ausente. Gere via OAuth antes de publicar automaticamente.")
            if not product_payload.get("category_id"):
                blockers.append("Mercado Livre: category_id ausente. Configure a categoria MLB correta do produto.")
            if not product_payload.get("listing_type_id"):
                blockers.append("Mercado Livre: listing_type_id ausente.")
        return blockers

    def can_upload_images_during_publish(
        self,
        connector: MarketplaceConnector,
        store: dict[str, Any],
        project: dict[str, Any],
        payload: ProductPublishRequest,
    ) -> bool:
        if payload.mode != "publish" or connector.marketplace != "mercado_livre":
            return False
        access_token = str(store.get("credentials", {}).get("access_token", "")).strip()
        return bool(access_token and self.resolve_local_product_images(project))

    def looks_like_mercado_livre_category_id(self, value: str) -> bool:
        return value.startswith("MLB") and value[3:].isdigit()

    def build_mercado_livre_attributes(self, category_id: str, project: dict[str, Any], channel: dict[str, Any]) -> list[dict[str, Any]]:
        if not category_id:
            return []
        category_attributes = self.fetch_mercado_livre_category_attributes(category_id)
        by_id = {item.get("id"): item for item in category_attributes if isinstance(item, dict)}
        required_ids = [
            item.get("id")
            for item in category_attributes
            if isinstance(item, dict) and (item.get("tags", {}).get("required") or item.get("tags", {}).get("catalog_required"))
        ]
        material = self.infer_material_name(project)
        manufacturer = "EuAchei3D"
        model_name = str(project.get("name") or channel.get("title") or "Modelo 3D")[:255]
        dimensions_cm = self.infer_dimensions_cm(project)
        weight_g = self.infer_weight_g(project)
        theme = self.infer_sculpture_theme(project, channel)
        character = self.infer_character_name(project, channel)
        with_base = self.infer_with_base(project)
        includes_hook = self.infer_includes_hook(project, channel)
        color = self.infer_color(project, channel)
        pattern_name = self.infer_pattern_name(project, channel)
        values_by_id: dict[str, Any] = {
            "BRAND": "Produção Própria Artesanal",
            "MANUFACTURER": manufacturer,
            "MODEL": model_name,
            "MATERIAL": material,
            "SCULPTURE_THEME": theme,
            "SCULPTURE_TYPE": "Estátua",
            "ARTWORK_TYPE": "Réplica",
            "CHARACTER": character,
        }
        if color:
            values_by_id["COLOR"] = color
        if pattern_name:
            values_by_id["PATTERN_NAME"] = pattern_name
        normalized: list[dict[str, Any]] = []
        for attribute_id in required_ids:
            attribute = by_id.get(attribute_id) or {}
            value_name = str(values_by_id.get(attribute_id, "")).strip()
            if not value_name:
                continue
            normalized.append(self.build_mercado_livre_attribute(attribute, value_name=value_name[:255]))

        # All optional attributes we want to proactively fill.
        # IDs confirmed via GET /categories/MLB439316/attributes on 2026-05-03.
        optional_ids = [
            "MATERIAL",
            "COLOR",
            "PATTERN_NAME",
            "SCULPTURE_THEME", "SCULPTURE_TYPE", "ARTWORK_TYPE", "CHARACTER",
            "LENGTH", "WIDTH", "HEIGHT", "WEIGHT",
            "WITH_BASE",
            "INCLUDES_HOOK",   # Inclui gancho
            "INCLUDES_STRAP",  # Inclui correia
            "PIECES_NUMBER",   # Quantidade de peças
            "MIN_RECOMMENDED_AGE",  # Idade mínima recomendada
        ]
        seen_ids = {item["id"] for item in normalized if item.get("id")}
        for attribute_id in optional_ids:
            if attribute_id in seen_ids:
                continue
            # Build a stub attribute dict if the category API returned empty (network failure).
            attribute = by_id.get(attribute_id) or {"id": attribute_id, "name": attribute_id}
            if attribute_id == "LENGTH" and dimensions_cm:
                normalized.append(self.build_mercado_livre_attribute(attribute, number=dimensions_cm[2], unit="cm"))
            elif attribute_id == "WIDTH" and dimensions_cm:
                normalized.append(self.build_mercado_livre_attribute(attribute, number=dimensions_cm[0], unit="cm"))
            elif attribute_id == "HEIGHT" and dimensions_cm:
                normalized.append(self.build_mercado_livre_attribute(attribute, number=dimensions_cm[1], unit="cm"))
            elif attribute_id == "WEIGHT" and weight_g:
                normalized.append(self.build_mercado_livre_attribute(attribute, number=weight_g, unit="g"))
            elif attribute_id == "WITH_BASE":
                normalized.append(self.build_mercado_livre_attribute(attribute, boolean_value=with_base))
            elif attribute_id == "INCLUDES_HOOK":
                normalized.append(self.build_mercado_livre_attribute(attribute, boolean_value=includes_hook))
            elif attribute_id == "INCLUDES_STRAP":
                normalized.append(self.build_mercado_livre_attribute(attribute, boolean_value=False))
            elif attribute_id == "PIECES_NUMBER":
                normalized.append(self.build_mercado_livre_attribute(attribute, number=1.0, unit=None))
            elif attribute_id == "MIN_RECOMMENDED_AGE":
                normalized.append(self.build_mercado_livre_attribute(attribute, number=3.0, unit="anos"))
            else:
                value_name = str(values_by_id.get(attribute_id, "")).strip()
                if value_name:
                    normalized.append(self.build_mercado_livre_attribute(attribute, value_name=value_name[:255]))
        # GTIN: aceita apenas códigos de barras reais (EAN-13, UPC-12, etc).
        # "Não se aplica" como value_name causa HTTP 400 item.attribute.product_identifier.invalid_format.
        # A forma correta é NÃO enviar GTIN e enviar EMPTY_GTIN_REASON em seu lugar.
        # Ref: categoria MLB439316: EMPTY_GTIN_REASON tem opção "O produto não tem código cadastrado".
        seen_ids = {item["id"] for item in normalized if item.get("id")}
        if "EMPTY_GTIN_REASON" in by_id and "EMPTY_GTIN_REASON" not in seen_ids and "GTIN" not in seen_ids:
            reason_attr = by_id["EMPTY_GTIN_REASON"]
            reason_value = "O produto não tem código cadastrado"
            option = self.match_mercado_livre_attribute_option(reason_attr, reason_value)
            if option:
                normalized.append({
                    "id": "EMPTY_GTIN_REASON",
                    "name": reason_attr.get("name", "Motivo de GTIN vazio"),
                    "value_id": option.get("id"),
                    "value_name": option.get("name"),
                })
            else:
                normalized.append({
                    "id": "EMPTY_GTIN_REASON",
                    "name": reason_attr.get("name", "Motivo de GTIN vazio"),
                    "value_name": reason_value,
                })
        return normalized

    def build_mercado_livre_attribute(
        self,
        attribute: dict[str, Any],
        *,
        value_name: str | None = None,
        number: float | None = None,
        unit: str | None = None,
        boolean_value: bool | None = None,
    ) -> dict[str, Any]:
        attribute_id = str(attribute.get("id") or "")
        payload: dict[str, Any] = {"id": attribute_id, "name": str(attribute.get("name") or attribute_id)}
        if boolean_value is not None:
            option = self.match_mercado_livre_attribute_option(attribute, "Sim" if boolean_value else "Não")
            if option:
                payload["value_id"] = option.get("id")
                payload["value_name"] = option.get("name")
                return payload
            payload["value_name"] = "Sim" if boolean_value else "Não"
            return payload
        if number is not None:
            if unit:
                payload["value_struct"] = {"number": round(float(number), 2), "unit": unit}
                payload["value_name"] = f"{round(float(number), 2):g} {unit}"
            else:
                payload["value_name"] = f"{round(float(number), 2):g}"
            return payload
        text = (value_name or "").strip()
        if text:
            option = self.match_mercado_livre_attribute_option(attribute, text)
            if option:
                payload["value_id"] = option.get("id")
                payload["value_name"] = option.get("name")
                return payload
            payload["value_name"] = text
        return payload

    def match_mercado_livre_attribute_option(self, attribute: dict[str, Any], value_name: str) -> dict[str, Any] | None:
        lowered = value_name.strip().lower()
        for option in attribute.get("values") or []:
            if str(option.get("name", "")).strip().lower() == lowered:
                return option
        return None

    # Maps raw material names (from 3D slicers / assumptions) to ML option names.
    # MLB439316 (Chaveiros): Aço, Plástico, Prata.
    # MLB186814 (Estatuetas): MATERIAL é value_type:string sem restricted_values —
    #   valores sugeridos são Argila/Bronze/Madeira etc., mas "Plástico" como texto
    #   livre (sem value_id) é aceito pela API pois não há restrição de valores.
    _MATERIAL_TO_ML: dict[str, str] = {
        "pla": "Plástico",
        "petg": "Plástico",
        "abs": "Plástico",
        "tpu": "Plástico",
        "nylon": "Plástico",
        "pc": "Plástico",
        "asa": "Plástico",
        "hips": "Plástico",
        "resin": "Plástico",
        "resina": "Plástico",
        "plastic": "Plástico",
        "plástico": "Plástico",
        "metal": "Aço",
        "steel": "Aço",
        "aço": "Aço",
        "silver": "Prata",
        "prata": "Prata",
    }

    def infer_material_name(self, project: dict[str, Any]) -> str:
        sales = project.get("sales_profile") or {}
        raw = "PLA"
        for assumption in sales.get("assumptions", []):
            text = str(assumption)
            if "Material assumido:" in text:
                raw = text.split("Material assumido:", 1)[1].split(".", 1)[0].strip() or "PLA"
                break
        return self._MATERIAL_TO_ML.get(raw.lower(), raw)

    def infer_includes_hook(self, project: dict[str, Any], channel: dict[str, Any]) -> bool:
        """Keychains include a hook by default; other items don't."""
        haystack = " ".join([
            str(project.get("name") or ""),
            str(channel.get("title") or ""),
            str(channel.get("category") or ""),
        ]).lower()
        return any(term in haystack for term in ["chaveiro", "keychain", "key chain", "gancho", "hook"])

    def infer_color(self, project: dict[str, Any], channel: dict[str, Any]) -> str:
        """Return a color name if inferable from the project, otherwise empty string."""
        sales = project.get("sales_profile") or {}
        # Use first variation name as color hint when available
        variations = list(sales.get("variations") or [])
        if variations and isinstance(variations[0], dict):
            name = str(variations[0].get("name") or "").strip()
            if name and len(name) <= 50:
                return name
        return ""

    def infer_pattern_name(self, project: dict[str, Any], channel: dict[str, Any]) -> str:
        """Return ML PATTERN_NAME from project name if it matches a known character."""
        haystack = " ".join([
            str(project.get("name") or ""),
            str(channel.get("title") or ""),
        ]).lower()
        known = [
            ("homem de ferro", "Homem de Ferro"),
            ("iron man", "Homem de Ferro"),
            ("batman", "Batman"),
            ("spider-man", "Homem-Aranha"), ("homem aranha", "Homem-Aranha"),
            ("hulk", "Hulk"),
            ("darth vader", "Darth Vader"),
        ]
        for keyword, ml_name in known:
            if keyword in haystack:
                return ml_name
        return ""

    def infer_dimensions_cm(self, project: dict[str, Any]) -> tuple[float, float, float] | None:
        mesh_metrics = project.get("metadata", {}).get("mesh_metrics", {})
        extents = mesh_metrics.get("extents_mm_assumed")
        if not isinstance(extents, list) or len(extents) < 3:
            return None
        try:
            x, y, z = [round(float(value) / 10.0, 1) for value in extents[:3]]
        except (TypeError, ValueError):
            return None
        if min(x, y, z) <= 0:
            return None
        return (x, y, z)

    def infer_weight_g(self, project: dict[str, Any]) -> float | None:
        sales = project.get("sales_profile") or {}
        value = sales.get("estimated_material_g")
        try:
            weight = round(float(value), 1)
        except (TypeError, ValueError):
            return None
        return weight if weight > 0 else None

    def infer_sculpture_theme(self, project: dict[str, Any], channel: dict[str, Any]) -> str:
        haystack = " ".join(
            [
                str(project.get("name") or ""),
                str(channel.get("title") or ""),
                str(channel.get("description") or ""),
            ]
        ).lower()
        if any(term in haystack for term in ["papagaio", "parrot", "bird", "pássaro", "passaro", "animal"]):
            return "Animais"
        if any(term in haystack for term in ["bola", "futebol", "soccer", "esporte"]):
            return "Esportes"
        return ""

    def infer_character_name(self, project: dict[str, Any], channel: dict[str, Any]) -> str:
        haystack = " ".join(
            [
                str(project.get("name") or ""),
                str(channel.get("title") or ""),
            ]
        ).lower()
        if "papagaio" in haystack or "parrot" in haystack:
            return "Papagaio"
        return ""

    def infer_with_base(self, project: dict[str, Any]) -> bool:
        haystack = " ".join([
            str(project.get("name") or ""),
            str(project.get("original_filename") or ""),
        ]).lower()
        return any(term in haystack for term in ["base", "stand", "pedestal", "plinth", "suporte"])

    def fetch_mercado_livre_category_attributes(self, category_id: str) -> list[dict[str, Any]]:
        request = Request(f"https://api.mercadolibre.com/categories/{category_id}/attributes", headers={"accept": "application/json"})
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []
        return payload if isinstance(payload, list) else []

    def limit_mercado_livre_images(self, category_id: str, images: list[str]) -> list[str]:
        max_pictures = self.fetch_mercado_livre_max_pictures(category_id)
        if max_pictures <= 0:
            max_pictures = 12
        return images[:max_pictures]

    def fetch_mercado_livre_max_pictures(self, category_id: str) -> int:
        if not category_id:
            return 12
        request = Request(f"https://api.mercadolibre.com/categories/{category_id}", headers={"accept": "application/json"})
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return 12
        settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
        value = settings.get("max_pictures_per_item")
        return int(value) if isinstance(value, int) else 12

    def predict_mercado_livre_category_id(
        self,
        store: dict[str, Any],
        project: dict[str, Any],
        title: str,
        channel: dict[str, Any],
    ) -> str:
        site_id = str(store.get("settings", {}).get("site_id") or "MLB").strip() or "MLB"
        queries = self.build_mercado_livre_prediction_queries(project, title, channel)
        for query in queries:
            if not query:
                continue
            url = f"https://api.mercadolibre.com/sites/{site_id}/domain_discovery/search?limit=1&q={quote(query)}"
            request = Request(url, headers={"accept": "application/json"})
            try:
                with urlopen(request, timeout=20) as response:  # noqa: S310
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if isinstance(payload, list) and payload:
                category_id = str(payload[0].get("category_id", "")).strip()
                if category_id:
                    return category_id
        # Fallback: MLB439316 = Chaveiros (Indústria e Comércio > Publicidade e
        # Promoção > Merchandising > Chaveiros) — produto principal desta loja.
        # Tem MATERIAL com opção "Plástico", EMPTY_GTIN_REASON, variações de cor, etc.
        return "MLB439316"

    def build_mercado_livre_prediction_queries(self, project: dict[str, Any], title: str, channel: dict[str, Any]) -> list[str]:
        project_name = str(project.get("name") or "").strip()
        sales = project.get("sales_profile") or {}
        marketplace_category = str(channel.get("category") or "").strip().lower()
        lowered = " ".join(part for part in [title.lower(), project_name.lower(), marketplace_category] if part)
        queries = [title, project_name, str(channel.get("category") or "").strip()]
        _decoration_terms = [
            "decorativo", "estatueta", "escultura", "enfeite", "ornamento",
            "miniatura", "figura decorativa", "parrot", "papagaio",
        ]
        _is_decoration = any(term in lowered for term in _decoration_terms)
        _is_mask = "máscara" in lowered or "mascara" in lowered or "helmet" in lowered or "capacete" in lowered
        _is_keychain = "chaveiro" in lowered or "porta chaves" in lowered or "keychain" in lowered
        name_for_query = project_name or title
        if _is_mask:
            queries = [
                f"{name_for_query} decoração cosplay",
                f"máscara decorativa {name_for_query}",
                *queries,
            ]
        elif _is_decoration and not _is_keychain:
            # Produto claramente decorativo (estatueta, enfeite, escultura...)
            queries = [
                f"{name_for_query} estatueta decorativa impresso em 3d",
                f"figura decorativa {name_for_query}",
                *queries,
            ]
        else:
            # Default: chaveiro impresso em 3D — produto principal desta loja.
            # Inclui: chaveiros explícitos, personagens, animais, itens sem categoria clara.
            queries = [
                f"{name_for_query} chaveiro impresso em 3d",
                "chaveiro impresso em 3d personalizado",
                *queries,
            ]
        assumptions = sales.get("assumptions", [])
        if any("Chaveiro / brinde pequeno" in str(item) for item in assumptions):
            queries.insert(0, "chaveiro impresso em 3d")
        return [query for idx, query in enumerate(queries) if query and query not in queries[:idx]]

    def missing_required_credentials(self, connector: MarketplaceConnector, credentials: dict[str, str]) -> list[str]:
        missing = []
        for field in connector.required_credentials:
            if field.required and not credentials.get(field.key):
                missing.append(f"Credencial obrigatória ausente: {field.label}.")
        return missing

    def infer_status(self, connector: MarketplaceConnector, credentials: dict[str, str]) -> str:
        return "configured" if not self.missing_required_credentials(connector, credentials) else "needs_credentials"

    def to_response(self, record: dict[str, Any]) -> StoreResponse:
        connector = self.get_connector(record["marketplace"])
        credentials = record.get("credentials", {})
        return StoreResponse(
            id=record["id"],
            owner_username=record["owner_username"],
            name=record["name"],
            marketplace=record["marketplace"],
            marketplace_label=connector.label,
            account_label=record.get("account_label"),
            status=record.get("status", "draft"),
            country=record.get("country", "BR"),
            currency=record.get("currency", "BRL"),
            credential_status=[
                StoreCredentialStatus(
                    key=field.key,
                    configured=bool(credentials.get(field.key)),
                    masked_value=self.mask_secret(credentials.get(field.key), field.secret),
                )
                for field in connector.required_credentials
            ],
            settings=record.get("settings", {}),
            created_at=datetime.fromisoformat(record["created_at"]),
            updated_at=datetime.fromisoformat(record["updated_at"]),
        )

    def get_connector(self, marketplace: str) -> MarketplaceConnector:
        for connector in self.list_connectors():
            if connector.marketplace == marketplace:
                return connector
        return self.list_connectors()[-1]

    def sanitize_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        return {key: value.strip() for key, value in credentials.items() if value and value.strip()}

    def mask_secret(self, value: str | None, secret: bool) -> str | None:
        if not value:
            return None
        if not secret:
            return value
        if len(value) <= 6:
            return "***"
        return f"{value[:2]}***{value[-4:]}"

    def _truncate_ml_title(self, title: str, limit: int = 60) -> str:
        """Truncate ML title at a word boundary, never cutting mid-word."""
        if len(title) <= limit:
            return title
        truncated = title[:limit]
        last_space = truncated.rfind(" ")
        return truncated[:last_space].rstrip() if last_space > 0 else truncated

    def matches_channel(self, marketplace: str, channel_name: str) -> bool:
        normalized = channel_name.lower()
        if marketplace == "mercado_livre":
            return "mercado" in normalized
        if marketplace == "shopee":
            return "shopee" in normalized
        if marketplace == "meta_instagram":
            return "instagram" in normalized or "meta" in normalized
        return False

    def load_store_records(self) -> list[dict[str, Any]]:
        if not self.data_path.exists():
            return []
        records = json.loads(self.data_path.read_text(encoding="utf-8"))
        migrated = False
        for record in records:
            if record.get("marketplace") != "mercado_livre":
                continue
            credentials = record.setdefault("credentials", {})
            settings = record.setdefault("settings", {})
            if not credentials.get("seller_id") and settings.get("id"):
                credentials["seller_id"] = str(settings.get("id"))
                migrated = True
        if migrated:
            self.write_store_records(records)
        return records

    def invalidate_store_token(self, store_id: str, keys: set[str]) -> None:
        records = self.load_store_records()
        changed = False
        for record in records:
            if record.get("id") != store_id:
                continue
            credentials = record.setdefault("credentials", {})
            for key in keys:
                if key in credentials:
                    credentials.pop(key, None)
                    changed = True
            record["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        if changed:
            self.write_store_records(records)

    def store_priority_score(self, store: dict[str, Any]) -> tuple[int, int, int, int, str]:
        credentials = store.get("credentials", {})
        settings = store.get("settings", {})
        status = str(store.get("status", "draft"))
        has_token = bool(credentials.get("access_token"))
        has_refresh = bool(credentials.get("refresh_token"))
        has_seller = bool(credentials.get("seller_id") or settings.get("id"))
        configured = 1 if status == "configured" else 0
        return (1 if has_token else 0, 1 if has_refresh else 0, 1 if has_seller else 0, configured, str(store.get("name", "")))

    def write_store_records(self, records: list[dict[str, Any]]) -> None:
        self.data_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
