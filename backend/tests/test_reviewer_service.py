"""Tests for ReviewerService."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.reviewer_service import ReviewerService


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_manifest(tmp_path: Path, project_id: str, status: str = "completed") -> Path:
    manifest_dir = tmp_path / project_id / f"{project_id}_v001"
    manifest_dir.mkdir(parents=True)
    manifest = {
        "id": project_id,
        "name": f"Projeto {project_id}",
        "status": status,
        "risks": [],
        "updated_at": "2025-01-01T00:00:00Z",
    }
    manifest_file = manifest_dir / "project.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_file


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_reviewer_get_report_returns_placeholder_when_no_report(tmp_path: Path) -> None:
    svc = ReviewerService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        report = svc.get_report()
    assert report["health_score"] is None
    assert isinstance(report["findings"], list)


def test_reviewer_collect_observability_empty_storage(tmp_path: Path) -> None:
    svc = ReviewerService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        data = svc._collect_observability_data()
    assert data["stats"]["total_projects"] == 0
    assert isinstance(data["errors"], list)
    assert isinstance(data["warnings"], list)


def test_reviewer_collect_finds_failed_projects(tmp_path: Path) -> None:
    _make_manifest(tmp_path, "proj-001", status="failed")
    _make_manifest(tmp_path, "proj-002", status="completed")

    svc = ReviewerService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        data = svc._collect_observability_data()

    assert data["stats"]["total_projects"] == 2
    assert data["stats"]["failed"] == 1
    assert data["stats"]["completed"] == 1
    assert len(data["failed_projects"]) == 1
    assert data["failed_projects"][0]["id"] == "proj-001"


def test_reviewer_collect_error_patterns_from_log(tmp_path: Path) -> None:
    log_dir = tmp_path / "proj-x" / "proj-x_v001" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "processing.log").write_text(
        "INFO: tudo ok\nERROR: falha ao processar geometria\nWARNING: mesh com buracos\n",
        encoding="utf-8",
    )

    svc = ReviewerService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        data = svc._collect_observability_data()

    assert any("falha ao processar geometria" in e for e in data["errors"])
    assert any("mesh com buracos" in w for w in data["warnings"])


def test_reviewer_deterministic_findings_high_failure_rate(tmp_path: Path) -> None:
    svc = ReviewerService()
    raw_data = {
        "errors": [],
        "warnings": [],
        "failed_projects": [],
        "slow_endpoints": [],
        "stats": {
            "total_projects": 10,
            "failed": 3,
            "completed": 7,
            "processing": 0,
            "failure_rate_pct": 30.0,
        },
    }
    result = svc._deterministic_findings(raw_data)
    assert result["health_score"] is not None
    assert any("taxa de falha" in f["title"].lower() for f in result["findings"])


def test_reviewer_deterministic_findings_no_issues() -> None:
    svc = ReviewerService()
    raw_data = {
        "errors": [],
        "warnings": [],
        "failed_projects": [],
        "slow_endpoints": [],
        "stats": {
            "total_projects": 5,
            "failed": 0,
            "completed": 5,
            "processing": 0,
            "failure_rate_pct": 0.0,
        },
    }
    result = svc._deterministic_findings(raw_data)
    assert result["health_score"] >= 90
    assert result["findings"] == []


def test_reviewer_persist_and_load_report(tmp_path: Path) -> None:
    svc = ReviewerService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        report = {
            "started_at": "2025-01-01T00:00:00Z",
            "completed_at": "2025-01-01T00:00:30Z",
            "provider": "test",
            "health_score": 85,
            "summary": "Tudo ok.",
            "findings": [],
            "priority_actions": [],
            "auto_fixes_applied": [],
            "raw_stats": {},
        }
        svc._persist_report(report)
        loaded = svc.get_report()

    assert loaded["health_score"] == 85
    assert loaded["summary"] == "Tudo ok."


def test_reviewer_run_review_uses_deterministic_fallback(tmp_path: Path) -> None:
    """run_review should succeed even if FreeAI is fully disabled."""
    svc = ReviewerService()

    # Mock free_ai to always return fallback
    mock_fallback = {
        "health_score": 75,
        "summary": "Fallback determinístico.",
        "findings": [],
        "priority_actions": [],
        "auto_fixes_applied": [],
    }
    svc.free_ai.generate_json_with_fallback = MagicMock(  # type: ignore[method-assign]
        return_value=(mock_fallback, {"selected_provider": "fallback", "attempts": []})
    )

    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc.run_review()

    assert result["health_score"] == 75
    assert isinstance(result["findings"], list)
    assert isinstance(result["priority_actions"], list)
