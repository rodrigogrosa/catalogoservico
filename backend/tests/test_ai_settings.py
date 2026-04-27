from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.main import app
from app.schemas.auth import UserCreateRequest
from app.services.user_service import UserService


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_runtime_settings() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    (settings.storage_root / "_system" / "ai_runtime.json").unlink(missing_ok=True)
    (settings.storage_root / "_system" / "users.json").unlink(missing_ok=True)
    yield
    get_settings.cache_clear()
    settings = get_settings()
    (settings.storage_root / "_system" / "ai_runtime.json").unlink(missing_ok=True)
    (settings.storage_root / "_system" / "users.json").unlink(missing_ok=True)


def master_token() -> str:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_ai_settings_requires_authentication() -> None:
    response = client.get("/api/v1/ai-settings")
    assert response.status_code == 401


def test_master_can_get_and_update_ai_settings() -> None:
    token = master_token()

    get_response = client.get("/api/v1/ai-settings", headers={"Authorization": f"Bearer {token}"})
    assert get_response.status_code == 200
    initial = get_response.json()
    assert "ollama" in initial["provider_order"]

    put_response = client.put(
        "/api/v1/ai-settings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "free_ai_enabled": True,
            "external_providers_enabled": True,
            "provider_order": ["huggingface", "pollinations", "ollama", "huggingface"],
        },
    )
    assert put_response.status_code == 200
    updated = put_response.json()
    assert updated["external_providers_enabled"] is True
    assert updated["provider_order"] == ["huggingface", "pollinations", "ollama"]
    assert updated["updated_at"]

    confirm = client.get("/api/v1/ai-settings", headers={"Authorization": f"Bearer {token}"})
    assert confirm.status_code == 200
    payload = confirm.json()
    assert payload["provider_order"] == ["huggingface", "pollinations", "ollama"]


def test_viewer_cannot_access_ai_settings() -> None:
    service = UserService()
    service.create_user(
        UserCreateRequest(
            username="viewer@example.com",
            display_name="Leitor",
            role="viewer",
            provider="local",
            password="viewer-pass",
            status="active",
        )
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "viewer@example.com", "password": "viewer-pass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client.get("/api/v1/ai-settings", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
