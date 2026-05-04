from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MarketplaceCode = Literal["mercado_livre", "shopee", "meta_instagram", "custom_store"]
StoreStatus = Literal["draft", "configured", "needs_credentials", "disabled"]


class ConnectorField(BaseModel):
    key: str
    label: str
    required: bool = True
    secret: bool = False
    help_text: str = ""
    help_url: str = ""
    group: str = "Credenciais"


class ConnectorCapability(BaseModel):
    key: str
    label: str
    implemented: bool
    notes: str = ""


class MarketplaceConnector(BaseModel):
    marketplace: MarketplaceCode
    label: str
    docs_url: str
    auth_type: str
    required_credentials: list[ConnectorField] = Field(default_factory=list)
    required_product_fields: list[str] = Field(default_factory=list)
    capabilities: list[ConnectorCapability] = Field(default_factory=list)
    implementation_notes: list[str] = Field(default_factory=list)


class StoreCredentialStatus(BaseModel):
    key: str
    configured: bool
    masked_value: str | None = None


class StoreCreateRequest(BaseModel):
    name: str
    marketplace: MarketplaceCode
    account_label: str | None = None
    country: str = "BR"
    currency: str = "BRL"
    credentials: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class StoreUpdateRequest(BaseModel):
    name: str | None = None
    account_label: str | None = None
    status: StoreStatus | None = None
    country: str | None = None
    currency: str | None = None
    credentials: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class StoreResponse(BaseModel):
    id: str
    owner_username: str
    name: str
    marketplace: MarketplaceCode
    marketplace_label: str
    account_label: str | None = None
    status: StoreStatus
    country: str = "BR"
    currency: str = "BRL"
    credential_status: list[StoreCredentialStatus] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class StoreOAuthAuthorizationResponse(BaseModel):
    store: StoreResponse
    authorization_url: str
    redirect_uri: str
    state: str
    instructions: list[str] = Field(default_factory=list)


class StoreOAuthCallbackResponse(BaseModel):
    store: StoreResponse
    status: str
    seller_id: str | None = None
    expires_in: int | None = None


class StoreListResponse(BaseModel):
    items: list[StoreResponse]


class ConnectorListResponse(BaseModel):
    items: list[MarketplaceConnector]


class ProductPublishRequest(BaseModel):
    mode: Literal["draft", "validate", "publish"] = "draft"
    price_override_brl: float | None = None
    stock: int = 1
    product_url: str | None = None
    image_base_url: str | None = None
    pre_uploaded_picture_ids: list[str] | None = None


class ProductPublishDraftResponse(BaseModel):
    status: Literal["draft_ready", "blocked", "not_implemented", "published"]
    store_id: str
    store_name: str
    marketplace: MarketplaceCode
    project_id: str
    can_publish: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    published_item_id: str | None = None
    published_permalink: str | None = None
    publication_reference: dict[str, Any] = Field(default_factory=dict)
