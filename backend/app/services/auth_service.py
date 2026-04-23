from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import urlencode

from app.core.config import get_settings
from app.schemas.auth import AuthUser, LoginResponse, OAuthProviderStatus


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def authenticate_master(self, username: str, password: str) -> LoginResponse | None:
        expected_user = self.settings.master_username
        valid_passwords = [self.settings.master_password, *self.settings.master_password_aliases]
        if not hmac.compare_digest(username.strip(), expected_user):
            return None
        if not any(hmac.compare_digest(password, valid_password) for valid_password in valid_passwords):
            return None

        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=self.settings.auth_token_ttl_hours)
        user = AuthUser(
            username=expected_user,
            display_name="Rodrigo Rosa",
            role="master",
            provider="master",
        )
        return LoginResponse(
            access_token=self.create_token(user, expires_at),
            expires_at=expires_at.isoformat(),
            user=user,
        )

    def create_token(self, user: AuthUser, expires_at: datetime) -> str:
        payload = {
            "sub": user.username,
            "name": user.display_name,
            "role": user.role,
            "provider": user.provider,
            "exp": int(expires_at.timestamp()),
        }
        encoded_payload = self.base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(
            self.settings.auth_token_secret.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{encoded_payload}.{signature}"

    def validate_token(self, token: str) -> AuthUser | None:
        if "." not in token:
            return None
        encoded_payload, signature = token.rsplit(".", 1)
        expected_signature = hmac.new(
            self.settings.auth_token_secret.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None

        try:
            payload = json.loads(base64.urlsafe_b64decode(self.pad_base64(encoded_payload)).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None

        if int(payload.get("exp", 0)) < int(datetime.now(tz=timezone.utc).timestamp()):
            return None

        return AuthUser(
            username=str(payload.get("sub", "")),
            display_name=str(payload.get("name", payload.get("sub", ""))),
            role=str(payload.get("role", "user")),
            provider=str(payload.get("provider", "unknown")),
        )

    def list_oauth_providers(self) -> list[OAuthProviderStatus]:
        return [
            self.build_provider_status(
                provider="google",
                label="Google",
                client_id=self.settings.google_oauth_client_id,
                redirect_uri=self.settings.google_oauth_redirect_uri,
                base_url="https://accounts.google.com/o/oauth2/v2/auth",
                scope="openid email profile",
                extra={"response_type": "code", "access_type": "offline", "prompt": "consent"},
            ),
            self.build_provider_status(
                provider="apple",
                label="Apple",
                client_id=self.settings.apple_oauth_client_id,
                redirect_uri=self.settings.apple_oauth_redirect_uri,
                base_url="https://appleid.apple.com/auth/authorize",
                scope="name email",
                extra={"response_type": "code", "response_mode": "form_post"},
            ),
            self.build_provider_status(
                provider="instagram",
                label="Instagram",
                client_id=self.settings.instagram_oauth_client_id,
                redirect_uri=self.settings.instagram_oauth_redirect_uri,
                base_url="https://api.instagram.com/oauth/authorize",
                scope="user_profile,user_media",
                extra={"response_type": "code"},
            ),
        ]

    def build_provider_status(
        self,
        provider: str,
        label: str,
        client_id: str,
        redirect_uri: str,
        base_url: str,
        scope: str,
        extra: dict[str, str],
    ) -> OAuthProviderStatus:
        if not client_id or not redirect_uri:
            return OAuthProviderStatus(
                provider=provider,
                label=label,
                enabled=False,
                reason="Configure client_id e redirect_uri para ativar este login social.",
            )
        query: dict[str, Any] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": "snapmaker3d-studio",
            **extra,
        }
        return OAuthProviderStatus(
            provider=provider,
            label=label,
            enabled=True,
            auth_url=f"{base_url}?{urlencode(query)}",
        )

    @staticmethod
    def base64url_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")

    @staticmethod
    def pad_base64(value: str) -> bytes:
        return f"{value}{'=' * (-len(value) % 4)}".encode("utf-8")
