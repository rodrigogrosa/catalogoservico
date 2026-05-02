from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services.storage_service import StorageService


def build_manifest(project_root: Path, project_id: str) -> dict:
    return {
        "id": project_id,
        "name": "Projeto Teste",
        "slug": "projeto-teste",
        "version": 1,
        "status": "uploaded",
        "input_format": "3mf",
        "source_ecosystem": "bambu_lab",
        "created_at": "2026-04-27T20:00:00+00:00",
        "updated_at": "2026-04-27T20:00:00+00:00",
        "preview_url": "/storage/projeto-teste/projeto-teste_v001/previews/preview.png",
        "printable_score": {"score": 100, "level": "low", "blockers": [], "warnings": [], "recommendations": []},
        "sales_profile": {
            "pricing_version": "x",
            "copy_source": "deterministic",
            "estimated_material_g": 100,
            "estimated_print_hours": 2,
            "estimated_base_cost_brl": 20,
            "suggested_price_50_margin_brl": 30,
            "reseller_price_brl": 25,
            "default_margin_percent": 50,
            "reseller_margin_percent": 25,
            "currency": "BRL",
            "assumptions": ["a"],
            "sales_tips": ["b"],
            "marketplace_attributes": [{"marketplace": "ml", "title": "t"}],
        },
        "storage_path": str(project_root),
        "original_filename": "sample.3mf",
        "size_bytes": 123,
        "input_files": [],
        "requested_actions": [],
        "findings": [],
        "risks": [],
        "questions_pending": [],
        "blocking_questions": [],
        "metadata": {},
        "processing_stages": [],
        "stage_metrics": [],
        "decisions": [],
        "artifacts": [],
        "previews": [],
        "reports": [],
        "logs": [],
        "bundles": [],
        "manifest": None,
        "snapshot": None,
        "bambu_parameter_equivalence": [],
    }


def test_save_manifest_writes_compact_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    storage = StorageService()
    layout = storage.create_project_layout("projeto-teste")
    manifest = build_manifest(layout["folders"]["root"], layout["version_name"])

    storage.save_manifest(manifest)

    summary_file = layout["folders"]["root"] / "project.summary.json"
    assert summary_file.exists()
    summary = storage.read_json(summary_file)
    assert summary["id"] == layout["version_name"]
    assert isinstance(summary["sales_profile"], dict), "sales_profile deve ser preservado no summary"
    assert summary["sales_profile"]["copy_source"] == "deterministic"
    assert "metadata" not in summary
    get_settings.cache_clear()


def test_list_manifests_uses_summary_when_project_json_is_broken(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    storage = StorageService()
    layout = storage.create_project_layout("projeto-teste")
    manifest = build_manifest(layout["folders"]["root"], layout["version_name"])
    storage.save_manifest(manifest)

    # Simula corrupção do manifesto completo sem quebrar o catálogo.
    (layout["folders"]["root"] / "project.json").write_text("{broken", encoding="utf-8")
    manifests = storage.list_manifests()

    assert len(manifests) == 1
    assert manifests[0]["id"] == layout["version_name"]
    assert manifests[0]["name"] == "Projeto Teste"
    get_settings.cache_clear()

