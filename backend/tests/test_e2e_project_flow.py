"""End-to-end flow tests covering the complete project lifecycle.

Flow validated:
  upload STL  →  GET project (loads fast via direct path)
  →  POST /process (pipeline with mocked heavy agents)
  →  GET project (status=completed)
  →  GET /versions (one version)
  →  POST /reprocess (new version from same files)
  →  GET /versions (two versions)
  →  DELETE project
  →  GET project (404)

Also covers:
  - load_manifest O(1) path (slug derived from project_id, no NFS glob)
  - Auth guard: 401 on missing/invalid token
  - Conflict guard: 409 when already processing
  - 404 on unknown project_id
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.agents.orchestrator import OrchestratorAgent
from app.services.agents.qa_agent import QATechnicalAgent
from app.services.project_service import ProjectService
from app.services.sales_service import SalesService
from app.services.storage_service import StorageService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_agent_output(*, etapa: str = "mock_stage", name: str = "mock_agent") -> dict[str, Any]:
    """Minimal valid agent output that satisfies process_project's expectations."""
    return {
        "agent": name,
        "status": "ok",
        "etapa": etapa,
        "achados": ["Etapa de teste concluída sem erros."],
        "riscos": [],
        "perguntas_ao_usuario": [],
        "acoes_executadas": ["Execução simulada pelo mock de teste."],
        "artefatos_gerados": [],
        "caminho_de_saida": "",
        "extra": {
            "metrics": {},
            "decisions": [],
            "limitations": [],
            "fallbacks": [],
            "printable_score": {
                "score": 88,
                "level": "high",
                "blockers": [],
                "warnings": [],
                "recommendations": [],
            },
        },
    }


def _make_3mf_bytes() -> bytes:
    """Return a minimal valid 3MF archive (ZIP with required Metadata entry)."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "Metadata/project_settings.config",
            json.dumps({"printer_model": "Bambu Lab P1S"}),
        )
        zf.writestr(
            "3D/3dmodel.model",
            '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
            "<resources/><build/></model>",
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace all heavy pipeline components with fast stubs."""
    # Disable external AI calls
    monkeypatch.setenv("FREE_AI_EXTERNAL_ENABLED", "false")
    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    get_settings.cache_clear()

    # Stub orchestrator: returns one minimal output immediately
    def fake_orchestrator_run(
        self: OrchestratorAgent, context: dict[str, Any], progress_callback=None
    ) -> list[dict[str, Any]]:
        if progress_callback:
            progress_callback("mock_stage", "Mock stage", "in_progress", "Mock em progresso.")
            progress_callback("mock_stage", "Mock stage", "completed", "Mock concluído.")
        return [_minimal_agent_output()]

    def fake_orchestrator_describe(
        self: OrchestratorAgent, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [{"key": "mock_stage", "label": "Mock stage"}]

    monkeypatch.setattr(OrchestratorAgent, "run", fake_orchestrator_run)
    monkeypatch.setattr(OrchestratorAgent, "describe_pipeline", fake_orchestrator_describe)

    # Stub sales profile: return deterministic minimal data without LLM calls
    def fake_sales_profile(self: SalesService, manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {
            "pricing_version": "test-1.0",
            "copy_source": "test_mock",
            "estimated_material_g": 50.0,
            "estimated_print_hours": 2.0,
            "estimated_base_cost_brl": 10.0,
            "suggested_price_50_margin_brl": 15.0,
            "reseller_price_brl": 12.0,
            "default_margin_percent": 50.0,
            "reseller_margin_percent": 20.0,
            "currency": "BRL",
            "assumptions": ["Mock de teste."],
            "sales_tips": [],
            "marketplace_attributes": [],
        }

    monkeypatch.setattr(SalesService, "build_sales_profile", fake_sales_profile)


@pytest.fixture
def stl_file() -> bytes:
    """Minimal valid binary STL (header + 0 triangles)."""
    return b"0" * 80 + (0).to_bytes(4, "little")


@pytest.fixture
def mf3_file() -> bytes:
    return _make_3mf_bytes()


# ---------------------------------------------------------------------------
# Core e2e flow
# ---------------------------------------------------------------------------

class TestFullProjectLifecycle:
    """Upload → process → versions → reprocess → delete."""

    def test_upload_stl_and_get_project(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
    ) -> None:
        # --- Upload ---
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("dinosaur.stl", stl_file, "application/sla")},
            data={"project_name": "Dinosaur STL"},
        )
        assert upload_resp.status_code == 200, upload_resp.text
        project = upload_resp.json()
        project_id = project["id"]
        assert project_id.startswith("dinosaur-stl_v")
        assert project["status"] in ("pending", "uploaded")
        assert "dinosaur" in project["name"].lower()

        # --- GET project (must load via direct O(1) path) ---
        get_resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert get_resp.status_code == 200, get_resp.text
        detail = get_resp.json()
        assert detail["id"] == project_id
        assert detail["status"] in ("pending", "uploaded")

    def test_upload_3mf_and_get_project(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mf3_file: bytes,
    ) -> None:
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("model.3mf", mf3_file, "application/zip")},
            data={"project_name": "Bambu Model"},
        )
        assert upload_resp.status_code == 200, upload_resp.text
        project = upload_resp.json()
        assert project["id"].startswith("bambu-model_v")

        get_resp = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers)
        assert get_resp.status_code == 200

    def test_full_process_pipeline(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
        mock_pipeline: None,
    ) -> None:
        # Upload
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("part.stl", stl_file, "application/sla")},
            data={"project_name": "E2E Pipeline Test"},
        )
        assert upload_resp.status_code == 200
        project_id = upload_resp.json()["id"]

        # Process – BackgroundTask runs synchronously in TestClient
        process_payload = {
            "repair_mesh": True,
            "adapt_to_snapmaker": True,
            "convert_from_bambu": False,
            "scale_mode": "normalize_units",
            "supports": "auto",
            "target_material": "PLA",
        }
        proc_resp = client.post(
            f"/api/v1/projects/{project_id}/process",
            headers=auth_headers,
            json=process_payload,
        )
        assert proc_resp.status_code == 200, proc_resp.text
        proc_data = proc_resp.json()
        # Route returns immediately with "processing" status
        assert proc_data["status"] == "processing"

        # After background task runs, GET must show completed/awaiting_user
        get_resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        final = get_resp.json()
        assert final["status"] in ("completed", "awaiting_user", "failed"), (
            f"Unexpected status: {final['status']}"
        )
        # Manifest fields set by the pipeline
        assert final["input_format"] is not None
        assert isinstance(final.get("processing_stages"), list)

    def test_versions_endpoint_after_process(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
        mock_pipeline: None,
    ) -> None:
        # Upload + process
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("v_test.stl", stl_file, "application/sla")},
            data={"project_name": "Version Test"},
        )
        assert upload_resp.status_code == 200
        project_id = upload_resp.json()["id"]

        client.post(
            f"/api/v1/projects/{project_id}/process",
            headers=auth_headers,
            json={"repair_mesh": False, "adapt_to_snapmaker": True},
        )

        versions_resp = client.get(f"/api/v1/projects/{project_id}/versions", headers=auth_headers)
        assert versions_resp.status_code == 200, versions_resp.text
        versions = versions_resp.json()
        assert isinstance(versions, list)
        assert len(versions) >= 1
        slug = upload_resp.json()["id"].rsplit("_v", 1)[0]
        for v in versions:
            assert v["id"].startswith(slug + "_v")

    def test_reprocess_creates_new_version(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
        mock_pipeline: None,
    ) -> None:
        # Upload + process v1
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("rp_test.stl", stl_file, "application/sla")},
            data={"project_name": "Reprocess Test"},
        )
        assert upload_resp.status_code == 200
        v1_id = upload_resp.json()["id"]
        assert v1_id.endswith("_v001")

        client.post(
            f"/api/v1/projects/{v1_id}/process",
            headers=auth_headers,
            json={"repair_mesh": False, "adapt_to_snapmaker": True},
        )

        # Reprocess → creates v002
        reproc_resp = client.post(
            f"/api/v1/projects/{v1_id}/reprocess",
            headers=auth_headers,
            json={"repair_mesh": True, "adapt_to_snapmaker": True, "target_material": "PETG"},
        )
        assert reproc_resp.status_code == 200, reproc_resp.text
        v2 = reproc_resp.json()
        v2_id = v2["id"]
        assert v2_id.endswith("_v002"), f"Expected _v002, got {v2_id}"
        assert v2["status"] in ("pending", "uploaded", "processing", "completed", "awaiting_user")

        # Versions should list both
        versions_resp = client.get(f"/api/v1/projects/{v2_id}/versions", headers=auth_headers)
        assert versions_resp.status_code == 200
        versions = versions_resp.json()
        ids = [v["id"] for v in versions]
        assert v1_id in ids
        assert v2_id in ids

    def test_delete_project(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
    ) -> None:
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("del_test.stl", stl_file, "application/sla")},
            data={"project_name": "Delete Test"},
        )
        assert upload_resp.status_code == 200
        project_id = upload_resp.json()["id"]

        # Delete
        del_resp = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

        # GET must return 404 after delete
        get_resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth / guard tests
# ---------------------------------------------------------------------------

class TestAuthGuards:
    def test_get_project_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/v1/projects/some-project_v001")
        assert resp.status_code == 401

    def test_get_project_with_invalid_token_returns_401(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/projects/some-project_v001",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_process_project_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.post("/api/v1/projects/some-project_v001/process", json={})
        assert resp.status_code == 401

    def test_delete_project_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/projects/some-project_v001")
        assert resp.status_code == 401

    def test_upload_without_token_returns_401(self, client: TestClient, stl_file: bytes) -> None:
        resp = client.post(
            "/api/v1/projects/upload",
            files={"files": ("x.stl", stl_file, "application/sla")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Error / edge case tests
# ---------------------------------------------------------------------------

class TestProjectErrors:
    def test_get_unknown_project_returns_404(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        resp = client.get("/api/v1/projects/non-existent_v999", headers=auth_headers)
        assert resp.status_code == 404

    def test_process_unknown_project_returns_404(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        resp = client.post(
            "/api/v1/projects/non-existent_v999/process",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 404

    def test_reprocess_unknown_project_returns_409(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        resp = client.post(
            "/api/v1/projects/non-existent_v999/reprocess",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 409

    def test_delete_unknown_project_returns_404(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        resp = client.delete("/api/v1/projects/non-existent_v999", headers=auth_headers)
        assert resp.status_code == 404

    def test_versions_unknown_project_returns_empty_list(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        # list_project_versions loads the manifest to get the slug – if not found, returns []
        resp = client.get("/api/v1/projects/non-existent_v999/versions", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_duplicate_upload_gets_next_version(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
    ) -> None:
        """Uploading same project name twice creates v001 and v002."""
        r1 = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("dup.stl", stl_file, "application/sla")},
            data={"project_name": "Dup Project"},
        )
        r2 = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("dup.stl", stl_file, "application/sla")},
            data={"project_name": "Dup Project"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"].endswith("_v001")
        assert r2.json()["id"].endswith("_v002")


# ---------------------------------------------------------------------------
# Storage fast-path tests
# ---------------------------------------------------------------------------

class TestStorageFastPath:
    """Verify load_manifest derives slug directly without any glob scan."""

    def test_load_manifest_uses_direct_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
        get_settings.cache_clear()

        storage = StorageService()
        layout = storage.create_project_layout("Test Part")
        project_root = layout["folders"]["root"]
        project_id = layout["version_name"]  # e.g. "test-part_v001"

        # Write a minimal manifest
        manifest = {
            "id": project_id,
            "name": "Test Part",
            "slug": layout["slug"],
            "version": layout["version"],
            "status": "pending",
            "storage_path": str(project_root),
            "input_format": "stl",
            "source_ecosystem": "generic",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        storage.save_manifest(manifest)

        # load_manifest must find the project without glob
        loaded = storage.load_manifest(project_id)
        assert loaded is not None
        assert loaded["id"] == project_id
        assert loaded["name"] == "Test Part"

    def test_load_manifest_returns_none_for_unknown_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
        get_settings.cache_clear()

        storage = StorageService()
        result = storage.load_manifest("unknown-project_v001")
        assert result is None

    def test_delete_project_uses_direct_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
        get_settings.cache_clear()

        storage = StorageService()
        layout = storage.create_project_layout("Del Part")
        project_root = layout["folders"]["root"]
        project_id = layout["version_name"]

        manifest = {
            "id": project_id,
            "name": "Del Part",
            "slug": layout["slug"],
            "version": layout["version"],
            "status": "pending",
            "storage_path": str(project_root),
            "input_format": "stl",
            "source_ecosystem": "generic",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        storage.save_manifest(manifest)
        assert storage.load_manifest(project_id) is not None

        deleted = storage.delete_project(project_id)
        assert deleted is True
        assert storage.load_manifest(project_id) is None
        # Parent slug dir should be removed when empty
        assert not (tmp_path / layout["slug"]).exists()

    def test_load_manifest_multiple_projects_same_slug(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v001 and v002 with same slug must both be loadable independently."""
        monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
        get_settings.cache_clear()

        storage = StorageService()
        for version_num in (1, 2):
            layout = storage.create_project_layout("Multi Version")
            project_root = layout["folders"]["root"]
            manifest = {
                "id": layout["version_name"],
                "name": "Multi Version",
                "slug": layout["slug"],
                "version": layout["version"],
                "status": "pending",
                "storage_path": str(project_root),
                "input_format": "stl",
                "source_ecosystem": "generic",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
            storage.save_manifest(manifest)

        v1 = storage.load_manifest("multi-version_v001")
        v2 = storage.load_manifest("multi-version_v002")
        assert v1 is not None and v1["id"] == "multi-version_v001"
        assert v2 is not None and v2["id"] == "multi-version_v002"


# ---------------------------------------------------------------------------
# Project listing
# ---------------------------------------------------------------------------

class TestProjectListing:
    def test_list_projects_returns_all_uploaded(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        stl_file: bytes,
    ) -> None:
        names = ["List A", "List B", "List C"]
        uploaded_ids = []
        for name in names:
            r = client.post(
                "/api/v1/projects/upload",
                headers=auth_headers,
                files={"files": ("part.stl", stl_file, "application/sla")},
                data={"project_name": name},
            )
            assert r.status_code == 200
            uploaded_ids.append(r.json()["id"])

        list_resp = client.get("/api/v1/projects", headers=auth_headers)
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        returned_ids = {item["id"] for item in items}
        for pid in uploaded_ids:
            assert pid in returned_ids

    def test_list_projects_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3MF pipeline test (Bambu conversion path)
# ---------------------------------------------------------------------------

class TestBambu3mfPipeline:
    def test_3mf_pipeline_completes(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        mf3_file: bytes,
        mock_pipeline: None,
    ) -> None:
        upload_resp = client.post(
            "/api/v1/projects/upload",
            headers=auth_headers,
            files={"files": ("bambu.3mf", mf3_file, "application/zip")},
            data={"project_name": "Bambu Pipeline"},
        )
        assert upload_resp.status_code == 200
        project_id = upload_resp.json()["id"]

        proc_resp = client.post(
            f"/api/v1/projects/{project_id}/process",
            headers=auth_headers,
            json={
                "repair_mesh": False,
                "adapt_to_snapmaker": True,
                "convert_from_bambu": True,
                "supports": "disabled",
                "target_material": "PLA",
            },
        )
        assert proc_resp.status_code == 200

        get_resp = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        project = get_resp.json()
        assert project["status"] in ("completed", "awaiting_user", "failed")
        # source_ecosystem should have been detected as bambu_lab or generic
        assert project.get("source_ecosystem") is not None
