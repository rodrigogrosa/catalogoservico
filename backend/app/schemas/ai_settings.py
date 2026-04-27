from __future__ import annotations

from pydantic import BaseModel, Field


class AiProviderState(BaseModel):
    key: str
    label: str
    provider_type: str
    enabled: bool
    description: str


class AiRuntimeSettingsResponse(BaseModel):
    free_ai_enabled: bool
    external_providers_enabled: bool
    provider_order: list[str] = Field(default_factory=list)
    providers: list[AiProviderState] = Field(default_factory=list)
    updated_at: str | None = None
    notes: list[str] = Field(default_factory=list)


class AiRuntimeSettingsUpdateRequest(BaseModel):
    free_ai_enabled: bool | None = None
    external_providers_enabled: bool | None = None
    provider_order: list[str] | None = None
