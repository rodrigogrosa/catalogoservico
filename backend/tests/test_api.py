from pathlib import Path
import shutil
import sys
from threading import Event, Thread
from time import perf_counter

from fastapi.testclient import TestClient


from app.core.config import get_settings
from app.main import app
from app.services.project_service import ProjectService


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    # /health is now lightweight — no llm_runtime (use /health/full for that)
    assert "pipeline_version" in payload
    assert "timestamp" in payload


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


def test_authenticated_upload_returns_request_id(auth_headers: dict) -> None:
    stl_payload = b"0" * 80 + (0).to_bytes(4, "little")

    response = client.post(
        "/api/v1/projects/upload",
        headers=auth_headers,
        files={"files": ("sample.stl", stl_payload, "application/sla")},
        data={"project_name": "Upload Test"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    payload = response.json()
    assert payload["id"].startswith("upload-test_v")
    # Sem cleanup manual — isolated_storage fixture (conftest.py) usa tmp_path


def test_login_survives_while_large_upload_is_processing(
    master_credentials: dict[str, str],
    monkeypatch,
) -> None:
    upload_started = Event()
    release_upload = Event()
    original = ProjectService.create_project_from_saved_files

    def delayed_create(self, saved_files, layout, project_name, origin_url):
        upload_started.set()
        release_upload.wait(timeout=5)
        return original(self, saved_files, layout, project_name, origin_url)

    monkeypatch.setattr(ProjectService, "create_project_from_saved_files", delayed_create)

    upload_client = TestClient(app)
    login_client = TestClient(app)

    login = login_client.post("/api/v1/auth/login", json=master_credentials)
    token = login.json()["access_token"]
    # Usa bytes menores para não alocar 42 MB em memória no processo de teste
    large_stl_payload = b"0" * 80 + (0).to_bytes(4, "little") + (b"x" * (512 * 1024))
    upload_response: dict[str, object] = {}

    def do_upload() -> None:
        upload_response["response"] = upload_client.post(
            "/api/v1/projects/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"files": ("large-sample.stl", large_stl_payload, "application/sla")},
            data={"project_name": "Large Upload Test"},
        )

    thread = Thread(target=do_upload, daemon=True)
    thread.start()
    assert upload_started.wait(timeout=2)

    started_at = perf_counter()
    second_login = login_client.post("/api/v1/auth/login", json=master_credentials)
    duration_seconds = perf_counter() - started_at

    release_upload.set()
    thread.join(timeout=10)

    assert second_login.status_code == 200
    assert duration_seconds < 1.5

    response = upload_response.get("response")
    assert response is not None
    assert response.status_code == 200
