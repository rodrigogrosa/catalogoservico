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
def clean_users_store() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    (settings.storage_root / "_system" / "users.json").unlink(missing_ok=True)
    yield
    get_settings.cache_clear()
    settings = get_settings()
    (settings.storage_root / "_system" / "users.json").unlink(missing_ok=True)


def master_token() -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def local_token(username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_only_master_can_mutate_users() -> None:
    service = UserService()
    service.create_user(
        UserCreateRequest(
            username="admin@portal.com",
            display_name="Admin",
            role="admin",
            provider="local",
            password="admin-pass",
            status="active",
        )
    )

    admin_token = local_token("admin@portal.com", "admin-pass")
    list_response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert list_response.status_code == 200

    create_response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "viewer@portal.com",
            "display_name": "Viewer",
            "role": "viewer",
            "provider": "local",
            "password": "viewer-pass",
            "status": "active",
            "granted_permissions": [],
            "revoked_permissions": [],
        },
    )
    assert create_response.status_code == 403
    assert "master" in create_response.json().get("detail", "").lower()


def test_master_can_create_and_update_user_permissions() -> None:
    token = master_token()

    create_response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "ops@portal.com",
            "display_name": "Operador",
            "role": "operator",
            "provider": "local",
            "password": "ops-pass",
            "status": "active",
            "granted_permissions": ["stores.view"],
            "revoked_permissions": ["projects.download"],
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["role"] == "operator"
    assert "stores.view" in created["permissions"]

    update_response = client.put(
        "/api/v1/users/local/ops%40portal.com",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "granted_permissions": ["users.view"],
            "revoked_permissions": [],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert "users.view" in updated["permissions"]
