from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.schemas.project import PrintableScore
from app.services.bundle_service import BundleService
from app.services.conversion_service import ConversionService
from app.services.project_service import ProjectService
from app.services.safe_parser_service import SafeParserService
from app.services.storage_service import StorageService


FIXTURES = Path(__file__).parent / "fixtures"


def test_fixture_corpus_detects_truncated_stl_and_missing_texture() -> None:
    parser = SafeParserService()
    result = parser.inspect_inputs(
        [
            FIXTURES / "truncated_ascii.stl",
            FIXTURES / "sample.obj",
            FIXTURES / "sample.mtl",
        ]
    )
    joined_errors = " ".join(result.errors + result.warnings).lower()
    assert "stl" in joined_errors
    assert "texture" in joined_errors
    assert result.linked_groups


def test_golden_bambu_equivalence_snapshot() -> None:
    service = ConversionService()
    settings = {
        "raft_first_layer_expansion": "-1",
        "solid_infill_filament": "0",
        "use_relative_e_distances": "1",
        "before_layer_change_gcode": "M117 Layer change",
    }
    _, _, equivalence = service._sanitize_project_settings(settings)
    simplified = [{"parameter": item["parameter"], "status": item["status"]} for item in equivalence]
    expected = json.loads((FIXTURES / "golden_bambu_equivalence.json").read_text(encoding="utf-8"))
    for item in expected:
        assert item in simplified


def test_compare_and_bundle_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    storage = StorageService()
    service = ProjectService()

    layout_a = storage.create_project_layout("sample-part")
    layout_b = storage.create_project_layout("sample-part")

    (layout_a["folders"]["export"] / "part_a.3mf").write_text("a", encoding="utf-8")
    (layout_b["folders"]["export"] / "part_b.3mf").write_text("b", encoding="utf-8")
    (layout_b["folders"]["reports"] / "report.md").write_text("# report", encoding="utf-8")
    (layout_b["folders"]["root"] / "project_manifest.json").write_text(
        json.dumps(
            {
                "project_id": layout_b["version_name"],
                "project_name": "sample-part",
                "slug": layout_b["slug"],
                "version": layout_b["version"],
                "created_at": "2026-04-13T00:10:00+00:00",
                "updated_at": "2026-04-13T00:10:00+00:00",
                "source_ecosystem": "generic",
                "input_formats": ["stl"],
                "pipeline_version": "0.3.0",
            }
        ),
        encoding="utf-8",
    )

    base_manifest = {
        "id": layout_a["version_name"],
        "name": "sample-part",
        "slug": layout_a["slug"],
        "version": layout_a["version"],
        "status": "completed",
        "input_format": "stl",
        "source_ecosystem": "generic",
        "created_at": "2026-04-13T00:00:00+00:00",
        "updated_at": "2026-04-13T00:00:00+00:00",
        "storage_path": str(layout_a["folders"]["root"]),
        "original_filename": "part.stl",
        "size_bytes": 1,
        "input_files": [],
        "requested_actions": [],
        "findings": [],
        "risks": [],
        "questions_pending": [],
        "blocking_questions": [],
        "metadata": {"request_parameters": {"supports": "auto", "scale_mode": "keep", "target_material": "PLA"}},
        "processing_stages": [],
        "stage_metrics": [],
        "decisions": [],
        "artifacts": [
            {"label": "part_a.3mf", "path": storage.to_storage_url(layout_a["folders"]["export"] / "part_a.3mf"), "kind": "export"}
        ],
        "previews": [],
        "reports": [],
        "logs": [],
        "bundles": [],
        "preview_url": None,
        "manifest": None,
        "snapshot": None,
        "bambu_parameter_equivalence": [],
        "printable_score": PrintableScore(score=82, level="medium", blockers=[], warnings=["thin wall"], recommendations=["use brim"]).model_dump(),
    }
    target_manifest = {
        **base_manifest,
        "id": layout_b["version_name"],
        "version": layout_b["version"],
        "updated_at": "2026-04-13T00:10:00+00:00",
        "storage_path": str(layout_b["folders"]["root"]),
        "metadata": {"request_parameters": {"supports": "disabled", "scale_mode": "fit_to_bed", "target_material": "PETG"}},
        "artifacts": [
            {"label": "part_b.3mf", "path": storage.to_storage_url(layout_b["folders"]["export"] / "part_b.3mf"), "kind": "export"}
        ],
        "reports": [
            {"label": "report.md", "path": storage.to_storage_url(layout_b["folders"]["reports"] / "report.md"), "kind": "report"}
        ],
        "printable_score": PrintableScore(score=91, level="low", blockers=[], warnings=[], recommendations=["ready"]).model_dump(),
    }

    storage.save_manifest(base_manifest)
    storage.save_manifest(target_manifest)

    comparison = service.compare_projects(layout_a["version_name"], layout_b["version_name"])
    assert comparison.parameter_changes["target_material"] == ["PLA", "PETG"]
    assert comparison.artifacts_added[0].label == "part_b.3mf"

    bundle = BundleService().build_project_bundle(layout_b["folders"]["root"])
    assert bundle["label"].endswith(".zip")
    assert (tmp_path / bundle["path"].split("/storage/", 1)[1]).exists()

    get_settings.cache_clear()
