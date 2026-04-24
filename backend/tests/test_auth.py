from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_social_login_config() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    path = settings.storage_root / "_system" / "social_login.json"
    path.unlink(missing_ok=True)
    yield
    get_settings.cache_clear()


def test_master_login_returns_bearer_token() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["role"] == "master"
    assert payload["access_token"]


def test_projects_require_authentication() -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_auth_me_accepts_master_token() -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    token = login.json()["access_token"]
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["role"] == "master"


def test_previous_master_password_alias_still_works() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Vilao2021@"},
    )
    assert response.status_code == 200


def test_oauth_providers_are_listed_as_configuration_contract() -> None:
    response = client.get("/api/v1/auth/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert {provider["provider"] for provider in providers} == {"google", "apple", "instagram"}


def test_social_login_configuration_requires_authentication() -> None:
    response = client.get("/api/v1/auth/social-config")
    assert response.status_code == 401


def test_social_login_configuration_lists_all_supported_providers() -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    token = login.json()["access_token"]
    response = client.get("/api/v1/auth/social-config", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert {provider["provider"] for provider in providers} == {"google", "apple", "instagram"}
    google = next(provider for provider in providers if provider["provider"] == "google")
    assert google["recommended_redirect_uri"].endswith("/api/v1/auth/oauth/google/callback")


def test_social_login_configuration_can_enable_google_provider() -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    token = login.json()["access_token"]
    response = client.put(
        "/api/v1/auth/social-config/google",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "credentials": {
                "client_id": "google-client-id.apps.googleusercontent.com",
                "client_secret": "google-secret",
            },
            "redirect_uri": "https://app.euachei3d.com.br/api/v1/auth/oauth/google/callback",
            "scopes": ["openid", "email", "profile"],
            "login_button_enabled": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "google"
    assert payload["status"] == "ready_for_oauth"
    assert payload["enabled"] is True
    assert payload["auth_url"]

    providers = client.get("/api/v1/auth/providers").json()["providers"]
    google = next(provider for provider in providers if provider["provider"] == "google")
    assert google["enabled"] is True
    assert "accounts.google.com" in google["auth_url"]


def test_social_oauth_callback_redirects_after_google_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    token = login.json()["access_token"]
    client.put(
        "/api/v1/auth/social-config/google",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "credentials": {
                "client_id": "google-client-id.apps.googleusercontent.com",
                "client_secret": "google-secret",
            },
            "redirect_uri": "https://api.euachei3d.com.br/api/v1/auth/oauth/google/callback",
            "scopes": ["openid", "email", "profile"],
            "login_button_enabled": True,
        },
    )

    class FakeResponse:
        def __init__(self, payload: dict[str, str], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code
            self.text = str(payload)

        def json(self) -> dict[str, str]:
            return self._payload

    def fake_post(*args, **kwargs):
        return FakeResponse({"access_token": "google-access-token"})

    def fake_get(*args, **kwargs):
        return FakeResponse(
            {
                "sub": "google-user-123",
                "email": "social@example.com",
                "name": "Usuário Google",
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    response = client.get(
        "/api/v1/auth/oauth/google/callback?code=abc123&state=snapmaker3d-studio",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/login/social-complete#session=" in response.headers["location"]


def test_social_oauth_callback_rejects_invalid_state() -> None:
    response = client.get("/api/v1/auth/oauth/google/callback?code=abc123&state=wrong-state")
    assert response.status_code == 400
    assert "State inválido" in response.text
