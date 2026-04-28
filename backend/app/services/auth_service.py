from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import httpx
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, quote

from app.core.config import get_settings
from app.schemas.auth import (
    AccessModelResponse,
    AuthUser,
    LoginResponse,
    OAuthProviderStatus,
    SocialLoginCredentialStatus,
    SocialLoginField,
    SocialLoginProviderConfig,
    SocialLoginProviderConfigUpdateRequest,
)
from app.services.user_service import UserService


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.user_service = UserService()
        self.data_dir = self.settings.storage_root / "_system"
        self.data_path = self.data_dir / "social_login.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def authenticate_master(self, username: str, password: str) -> LoginResponse | None:
        expected_user = self.settings.master_username
        valid_passwords = [self.settings.master_password, *self.settings.master_password_aliases]
        normalized_username = username.strip()
        if hmac.compare_digest(normalized_username, expected_user) and any(
            hmac.compare_digest(password, valid_password) for valid_password in valid_passwords
        ):
            return self.issue_session(self.user_service.master_user())

        local_user = self.user_service.authenticate_local(normalized_username, password)
        if local_user is None:
            return None
        return self.issue_session(local_user)

    def authenticate_social_user(
        self,
        *,
        provider: str,
        subject: str,
        email: str | None,
        display_name: str | None,
    ) -> LoginResponse:
        username = (email or f"{provider}:{subject}").strip()
        label = (display_name or email or subject).strip()
        user = self.user_service.ensure_social_user(username=username, display_name=label, provider=provider)
        return self.issue_session(user)

    def issue_session(self, user: AuthUser) -> LoginResponse:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=self.settings.auth_token_ttl_hours)
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

    def current_user_from_token(self, token: str) -> AuthUser | None:
        basic = self.validate_token(token)
        if basic is None:
            return None
        resolved = self.user_service.resolve_authenticated_user(
            username=basic.username,
            provider=basic.provider,
            display_name=basic.display_name,
        )
        return resolved

    def access_model(self) -> AccessModelResponse:
        return self.user_service.access_model()

    def list_oauth_providers(self) -> list[OAuthProviderStatus]:
        return [self.to_oauth_status(config) for config in self.list_social_provider_configs()]

    def list_social_provider_configs(self) -> list[SocialLoginProviderConfig]:
        records = self.load_provider_records()
        return [self.build_provider_config(definition, records.get(definition["provider"], {})) for definition in self.provider_definitions()]

    def update_social_provider_config(
        self,
        provider: str,
        payload: SocialLoginProviderConfigUpdateRequest,
    ) -> SocialLoginProviderConfig | None:
        definitions = {definition["provider"]: definition for definition in self.provider_definitions()}
        definition = definitions.get(provider)
        if definition is None:
            return None

        records = self.load_provider_records()
        current = dict(records.get(provider, {}))
        credentials = {**current.get("credentials", {})}
        settings = {**current.get("settings", {})}

        for key, value in payload.credentials.items():
            normalized = value.strip()
            if normalized:
                credentials[key] = normalized
            else:
                credentials.pop(key, None)

        if payload.redirect_uri is not None:
            normalized_redirect = payload.redirect_uri.strip()
            if normalized_redirect:
                settings["redirect_uri"] = normalized_redirect
            else:
                settings.pop("redirect_uri", None)

        if payload.scopes is not None:
            normalized_scopes = [scope.strip() for scope in payload.scopes if scope.strip()]
            if normalized_scopes:
                settings["scopes"] = normalized_scopes
            else:
                settings.pop("scopes", None)

        if payload.login_button_enabled is not None:
            settings["login_button_enabled"] = payload.login_button_enabled

        settings["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        records[provider] = {"credentials": credentials, "settings": settings}
        self.write_provider_records(records)
        return self.build_provider_config(definition, records[provider])

    def build_provider_config(self, definition: dict[str, Any], record: dict[str, Any]) -> SocialLoginProviderConfig:
        credentials = {**self.env_credentials_for_provider(definition["provider"]), **record.get("credentials", {})}
        settings = record.get("settings", {})
        redirect_uri = settings.get("redirect_uri") or self.recommended_redirect_uri(definition["provider"])
        scopes = settings.get("scopes") or list(definition["default_scopes"])
        login_button_enabled = bool(settings.get("login_button_enabled", False))

        required_keys = [field.key for field in definition["fields"] if field.required]
        configured_required = [key for key in required_keys if credentials.get(key)]
        all_required_present = len(configured_required) == len(required_keys)

        if all_required_present and login_button_enabled:
            status = "ready_for_oauth"
            reason = "Configuração salva e botão liberado na tela de login."
        elif all_required_present:
            status = "configured"
            reason = "Credenciais salvas. Ative o botão de login quando quiser testar o provedor."
        elif configured_required:
            status = "partial"
            reason = "Configuração parcial. Falta preencher pelo menos um campo obrigatório."
        else:
            status = "not_configured"
            reason = "Ainda não configurado. Use esta tela para salvar as credenciais do provedor."

        auth_url = None
        if all_required_present and login_button_enabled:
            client_id = str(credentials.get("client_id") or credentials.get("service_id") or "")
            query = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": self.scope_param(definition["provider"], scopes),
                "state": self._make_oauth_state(definition["provider"]),
                **definition["auth_extra"],
            }
            auth_url = f"{definition['auth_base_url']}?{urlencode(query)}"

        return SocialLoginProviderConfig(
            provider=definition["provider"],
            label=definition["label"],
            status=status,
            enabled=status == "ready_for_oauth",
            login_button_enabled=login_button_enabled,
            auth_url=auth_url,
            reason=reason,
            docs_url=definition["docs_url"],
            console_url=definition["console_url"],
            recommended_redirect_uri=self.recommended_redirect_uri(definition["provider"]),
            redirect_uri=redirect_uri,
            callback_uri=self.recommended_redirect_uri(definition["provider"]),
            scopes=scopes,
            fields=[
                field.model_copy(
                    update={
                        "current_value": None if field.secret else str(credentials.get(field.key, "") or ""),
                    }
                )
                for field in definition["fields"]
            ],
            credential_status=[
                SocialLoginCredentialStatus(
                    key=field.key,
                    label=field.label,
                    configured=bool(credentials.get(field.key)),
                    masked_value=self.mask_value(str(credentials.get(field.key, "")), field.secret),
                )
                for field in definition["fields"]
            ],
            notes=definition["notes"],
        )

    def to_oauth_status(self, config: SocialLoginProviderConfig) -> OAuthProviderStatus:
        if config.enabled and config.auth_url:
            return OAuthProviderStatus(
                provider=config.provider,
                label=config.label,
                enabled=True,
                auth_url=config.auth_url,
            )
        return OAuthProviderStatus(
            provider=config.provider,
            label=config.label,
            enabled=False,
            reason=config.reason,
        )

    def _make_oauth_state(self, provider: str) -> str:
        """Gera state HMAC-assinado com timestamp – compatível com _verify_oauth_state em auth.py."""
        import time as _time
        ts = str(int(_time.time()))
        raw = f"{provider}:{ts}"
        sig = hmac.new(self.settings.auth_token_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
        return f"{raw}:{sig}"

    def recommended_redirect_uri(self, provider: str) -> str:
        return f"{self.settings.public_backend_origin.rstrip('/')}/api/v1/auth/oauth/{provider}/callback"

    def frontend_origin(self) -> str:
        configured = self.settings.public_frontend_origin.rstrip("/")
        backend = self.settings.public_backend_origin.rstrip("/")

        if configured and not (
            configured.startswith("http://127.0.0.1")
            or configured.startswith("http://localhost")
        ):
            return configured

        if "://api." in backend:
            return backend.replace("://api.", "://app.", 1)
        if "http--backend--" in backend:
            return backend.replace("http--backend--", "http--frontend--", 1)
        return configured or backend

    def build_social_completion_url(self, session: LoginResponse) -> str:
        payload = self.base64url_encode(session.model_dump_json().encode("utf-8"))
        return f"{self.frontend_origin()}/login/social-complete#session={quote(payload)}"

    def callback_error_html(self, provider: str, status_label: str, message: str, *, code: str | None, state: str | None, status_code: int) -> str:
        title = f"Callback {provider.title()}"
        return f"""
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
              a {{ color: #9a3412; font-weight: 700; }}
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
              <p><a href="{self.frontend_origin()}">Voltar ao SnapMaker3d Studio</a></p>
            </main>
          </body>
        </html>
        """

    def exchange_google_code(self, code: str) -> LoginResponse:
        records = self.load_provider_records().get("google", {})
        credentials = {
            **self.env_credentials_for_provider("google"),
            **records.get("credentials", {}),
        }
        settings = records.get("settings", {})
        client_id = str(credentials.get("client_id") or "").strip()
        client_secret = str(credentials.get("client_secret") or "").strip()
        redirect_uri = str(settings.get("redirect_uri") or self.recommended_redirect_uri("google")).strip()

        if not client_id or not client_secret:
            raise ValueError("Google ainda não está configurado com Client ID e Client Secret.")

        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=20.0,
        )
        if token_response.status_code >= 400:
            detail = token_response.text.strip() or "Falha ao trocar code por token."
            raise ValueError(f"Google recusou a troca do authorization code. {detail}")

        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Google respondeu sem access_token.")

        profile_response = httpx.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=20.0,
        )
        if profile_response.status_code >= 400:
            detail = profile_response.text.strip() or "Falha ao consultar perfil do Google."
            raise ValueError(f"Google retornou erro ao buscar o perfil do usuário. {detail}")

        profile = profile_response.json()
        subject = str(profile.get("sub") or "").strip()
        if not subject:
            raise ValueError("Google respondeu sem identificador do usuário.")

        return self.authenticate_social_user(
            provider="google",
            subject=subject,
            email=str(profile.get("email") or "").strip() or None,
            display_name=str(profile.get("name") or "").strip() or None,
        )

    def provider_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "provider": "google",
                "label": "Google",
                "docs_url": "https://developers.google.com/identity/protocols/oauth2/web-server",
                "console_url": "https://console.cloud.google.com/apis/credentials",
                "auth_base_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "default_scopes": ["openid", "email", "profile"],
                "auth_extra": {"response_type": "code", "access_type": "offline", "prompt": "consent"},
                "fields": [
                    SocialLoginField(
                        key="client_id",
                        label="OAuth Client ID",
                        placeholder="1234567890-abc.apps.googleusercontent.com",
                        help_text="Crie credenciais do tipo Web application e copie o Client ID.",
                        help_url="https://developers.google.com/identity/oauth2/web/guides/get-google-api-clientid",
                    ),
                    SocialLoginField(
                        key="client_secret",
                        label="Client Secret",
                        secret=True,
                        placeholder="GOCSPX-...",
                        help_text="O Client Secret é necessário para a troca server-side do authorization code.",
                        help_url="https://developers.google.com/identity/protocols/oauth2/web-server",
                    ),
                ],
                "notes": [
                    "Adicione o domínio público do sistema em Authorized JavaScript origins no Google Cloud.",
                    "Cadastre exatamente a Redirect URI recomendada abaixo em Authorized redirect URIs.",
                    "Se quiser testar localmente, crie também uma credencial separada para localhost.",
                ],
            },
            {
                "provider": "apple",
                "label": "Apple",
                "docs_url": "https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple",
                "console_url": "https://developer.apple.com/account/resources/identifiers/list",
                "auth_base_url": "https://appleid.apple.com/auth/authorize",
                "default_scopes": ["name", "email"],
                "auth_extra": {"response_type": "code", "response_mode": "form_post"},
                "fields": [
                    SocialLoginField(
                        key="client_id",
                        label="Services ID / Client ID",
                        placeholder="com.euachei3d.web",
                        help_text="No login web da Apple, o client_id normalmente é o Services ID.",
                        help_url="https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web/",
                    ),
                    SocialLoginField(
                        key="team_id",
                        label="Apple Team ID",
                        placeholder="1A2BC3D4E5",
                        help_text="Necessário para gerar o client secret JWT do Sign in with Apple.",
                        help_url="https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple",
                    ),
                    SocialLoginField(
                        key="key_id",
                        label="Key ID",
                        placeholder="ABC123XYZ9",
                        help_text="É o identificador da chave privada criada para Sign in with Apple.",
                        help_url="https://developer.apple.com/help/account/configure-app-capabilities/create-a-sign-in-with-apple-private-key/",
                    ),
                    SocialLoginField(
                        key="private_key",
                        label="Private Key (.p8)",
                        secret=True,
                        group="Chave privada",
                        placeholder="-----BEGIN PRIVATE KEY-----",
                        help_text="Cole o conteúdo da chave .p8 em formato PEM.",
                        help_url="https://developer.apple.com/help/account/configure-app-capabilities/create-a-sign-in-with-apple-private-key/",
                    ),
                ],
                "notes": [
                    "A Apple exige HTTPS real para web e não aceita localhost/IP como redirect web.",
                    "Você precisa criar um Services ID, associar domínios e return URLs e gerar a chave privada.",
                    "Este projeto já deixa a Redirect URI pronta; falta cadastrar a mesma URI na Apple.",
                ],
            },
            {
                "provider": "instagram",
                "label": "Instagram",
                "docs_url": "https://developers.facebook.com/docs/instagram-platform",
                "console_url": "https://developers.facebook.com/apps/",
                "auth_base_url": "https://api.instagram.com/oauth/authorize",
                "default_scopes": ["user_profile", "user_media"],
                "auth_extra": {"response_type": "code"},
                "fields": [
                    SocialLoginField(
                        key="client_id",
                        label="App ID / Client ID",
                        placeholder="123456789012345",
                        help_text="Crie um app na Meta for Developers e ative o produto do Instagram usado na integração.",
                        help_url="https://developers.facebook.com/apps/",
                    ),
                    SocialLoginField(
                        key="client_secret",
                        label="App Secret",
                        secret=True,
                        placeholder="app-secret",
                        help_text="O App Secret é necessário para trocar o code por token no backend.",
                        help_url="https://developers.facebook.com/apps/",
                    ),
                ],
                "notes": [
                    "Use a mesma Redirect URI recomendada abaixo dentro do app da Meta.",
                    "Dependendo do produto habilitado na Meta, os escopos e a revisão do app podem variar.",
                    "Para produção, confirme no dashboard da Meta se o fluxo será Instagram Login ou outro produto equivalente.",
                ],
            },
        ]

    def env_credentials_for_provider(self, provider: str) -> dict[str, str]:
        if provider == "google":
            return {
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": "",
            }
        if provider == "apple":
            return {
                "client_id": self.settings.apple_oauth_client_id,
            }
        if provider == "instagram":
            return {
                "client_id": self.settings.instagram_oauth_client_id,
                "client_secret": "",
            }
        return {}

    def load_provider_records(self) -> dict[str, Any]:
        if not self.data_path.exists():
            return {}
        try:
            payload = json.loads(self.data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def write_provider_records(self, records: dict[str, Any]) -> None:
        self.data_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    def scope_param(self, provider: str, scopes: list[str]) -> str:
        delimiter = "," if provider == "instagram" else " "
        return delimiter.join(scopes)

    @staticmethod
    def mask_value(value: str, secret: bool) -> str | None:
        if not value:
            return None
        if not secret:
            if len(value) <= 10:
                return value
            return f"{value[:6]}...{value[-4:]}"
        if len(value) <= 8:
            return "•" * len(value)
        return f"{'•' * 8}{value[-4:]}"

    @staticmethod
    def base64url_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")

    @staticmethod
    def pad_base64(value: str) -> bytes:
        return f"{value}{'=' * (-len(value) % 4)}".encode("utf-8")
