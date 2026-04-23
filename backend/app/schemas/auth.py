from __future__ import annotations

from pydantic import BaseModel


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
