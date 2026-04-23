from pathlib import Path
import shutil
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "llm_runtime" in payload


def test_readiness_endpoint() -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert "slicer_target" in payload


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "SnapMaker3d Studio API"
    assert response.headers["x-request-id"]


def test_authenticated_upload_returns_request_id() -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "rodrigogrosa", "password": "Violao2021@"},
    )
    token = login.json()["access_token"]
    stl_payload = b"0" * 80 + (0).to_bytes(4, "little")

    response = client.post(
        "/api/v1/projects/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"files": ("sample.stl", stl_payload, "application/sla")},
        data={"project_name": "Upload Test"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    payload = response.json()
    assert payload["id"].startswith("upload-test_v")
    shutil.rmtree(Path(payload["storage_path"]), ignore_errors=True)
    project_parent = Path(payload["storage_path"]).parent
    if project_parent.exists() and not any(project_parent.iterdir()):
        project_parent.rmdir()
