from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app


client = TestClient(app)


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
