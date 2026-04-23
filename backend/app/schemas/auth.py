from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    username: str
    display_name: str
    role: str
    provider: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: AuthUser


class OAuthProviderStatus(BaseModel):
    provider: str
    label: str
    enabled: bool
    auth_url: str | None = None
    reason: str | None = None


class OAuthProvidersResponse(BaseModel):
    providers: list[OAuthProviderStatus]


class SocialLoginField(BaseModel):
    key: str
    label: str
    required: bool = True
    secret: bool = False
    group: str = "Credenciais"
    current_value: str | None = None
    placeholder: str | None = None
    help_text: str | None = None
    help_url: str | None = None


class SocialLoginCredentialStatus(BaseModel):
    key: str
    label: str
    configured: bool
    masked_value: str | None = None


class SocialLoginProviderConfig(BaseModel):
    provider: str
    label: str
    status: str
    enabled: bool
    login_button_enabled: bool
    auth_url: str | None = None
    reason: str | None = None
    docs_url: str
    console_url: str
    recommended_redirect_uri: str
    redirect_uri: str
    callback_uri: str
    scopes: list[str]
    fields: list[SocialLoginField]
    credential_status: list[SocialLoginCredentialStatus]
    notes: list[str] = Field(default_factory=list)


class SocialLoginProviderConfigUpdateRequest(BaseModel):
    credentials: dict[str, str] = Field(default_factory=dict)
    redirect_uri: str | None = None
    scopes: list[str] | None = None
    login_button_enabled: bool | None = None


class SocialLoginProviderConfigsResponse(BaseModel):
    providers: list[SocialLoginProviderConfig]
