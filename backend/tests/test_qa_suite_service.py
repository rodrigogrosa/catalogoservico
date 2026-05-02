"""Tests for QASuiteService."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.qa_suite_service import QASuiteService


# ── Helpers ───────────────────────────────────────────────────────────────────


class _MockProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ── get_last_result ────────────────────────────────────────────────────────────


def test_qa_suite_get_last_result_no_file(tmp_path: Path) -> None:
    svc = QASuiteService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc.get_last_result()
    assert result["overall_status"] == "never_run"
    assert result["layers"] == []


def test_qa_suite_get_last_result_with_file(tmp_path: Path) -> None:
    svc = QASuiteService()
    system_dir = tmp_path / "_system"
    system_dir.mkdir()
    data = {
        "overall_status": "passed",
        "total_duration_ms": 1234,
        "layers": [],
    }
    (system_dir / "qa_suite_result.json").write_text(json.dumps(data), encoding="utf-8")
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc.get_last_result()
    assert result["overall_status"] == "passed"
    assert result["total_duration_ms"] == 1234


# ── pytest layer ──────────────────────────────────────────────────────────────


def test_qa_suite_pytest_layer_passes(tmp_path: Path) -> None:
    svc = QASuiteService()
    mock_proc = _MockProcess(
        returncode=0,
        stdout="4 passed in 0.5s\n",
        stderr="",
    )
    with patch("subprocess.run", return_value=mock_proc):
        result = svc._run_pytest()

    assert result["name"] == "pytest"
    assert result["status"] == "passed"
    assert result["passed"] == 4


def test_qa_suite_pytest_layer_fails(tmp_path: Path) -> None:
    svc = QASuiteService()
    mock_proc = _MockProcess(
        returncode=1,
        stdout="2 passed, 1 failed in 0.8s\n",
        stderr="",
    )
    with patch("subprocess.run", return_value=mock_proc):
        result = svc._run_pytest()

    assert result["status"] == "failed"
    assert result["passed"] == 2
    assert result["failed"] == 1


def test_qa_suite_pytest_layer_timeout() -> None:
    import subprocess
    svc = QASuiteService()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=180)):
        result = svc._run_pytest()
    assert result["status"] == "error"
    assert "Timeout" in result.get("error", "")


# ── tsc layer ─────────────────────────────────────────────────────────────────


def test_qa_suite_tsc_layer_skipped_no_frontend(tmp_path: Path) -> None:
    svc = QASuiteService()
    # Override workspace root to tmp_path which has no frontend/
    svc._workspace_root = tmp_path
    result = svc._run_tsc()
    assert result["status"] == "skipped"


def test_qa_suite_tsc_layer_passes(tmp_path: Path) -> None:
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    svc = QASuiteService()
    svc._workspace_root = tmp_path

    mock_proc = _MockProcess(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=mock_proc):
        result = svc._run_tsc()

    assert result["status"] == "passed"


def test_qa_suite_tsc_layer_fails_with_ts_errors(tmp_path: Path) -> None:
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    svc = QASuiteService()
    svc._workspace_root = tmp_path

    mock_proc = _MockProcess(
        returncode=2,
        stdout="file.ts(1,1): error TS2304: Cannot find name 'x'.\n",
        stderr="",
    )
    with patch("subprocess.run", return_value=mock_proc):
        result = svc._run_tsc()

    assert result["status"] == "failed"
    assert result["failed"] == 1


# ── infra layer ───────────────────────────────────────────────────────────────


def test_qa_suite_infra_layer_storage_ok(tmp_path: Path) -> None:
    svc = QASuiteService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc._run_infra()

    storage_check = next((c for c in result.get("checks", []) if c["label"] == "storage_root_exists"), None)
    assert storage_check is not None
    assert storage_check["ok"] is True

    write_check = next((c for c in result.get("checks", []) if c["label"] == "storage_writable"), None)
    assert write_check is not None
    assert write_check["ok"] is True


def test_qa_suite_infra_layer_storage_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    svc = QASuiteService()
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: missing)):
        result = svc._run_infra()

    assert result["status"] == "failed"
    storage_check = next((c for c in result.get("checks", []) if c["label"] == "storage_root_exists"), None)
    assert storage_check is not None
    assert storage_check["ok"] is False


# ── run_suite integration ─────────────────────────────────────────────────────


def test_qa_suite_run_suite_persists_result(tmp_path: Path) -> None:
    svc = QASuiteService()

    # Stub all layer methods to return quickly
    svc._run_pytest = MagicMock(return_value={"name": "pytest", "status": "passed", "duration_ms": 10, "passed": 5, "failed": 0})  # type: ignore[method-assign]
    svc._run_smoke = MagicMock(return_value={"name": "smoke", "status": "passed", "duration_ms": 5, "passed": 3, "failed": 0})  # type: ignore[method-assign]
    svc._run_tsc = MagicMock(return_value={"name": "tsc", "status": "passed", "duration_ms": 20, "passed": 1, "failed": 0})  # type: ignore[method-assign]
    svc._run_infra = MagicMock(return_value={"name": "infra", "status": "passed", "duration_ms": 2, "passed": 4, "failed": 0})  # type: ignore[method-assign]

    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc.run_suite()

    assert result["overall_status"] == "passed"
    assert len(result["layers"]) == 4

    # Check persistence
    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        loaded = svc.get_last_result()
    assert loaded["overall_status"] == "passed"


def test_qa_suite_run_suite_subset(tmp_path: Path) -> None:
    svc = QASuiteService()

    svc._run_pytest = MagicMock(return_value={"name": "pytest", "status": "passed", "duration_ms": 1, "passed": 1, "failed": 0})  # type: ignore[method-assign]
    svc._run_infra = MagicMock(return_value={"name": "infra", "status": "passed", "duration_ms": 1, "passed": 1, "failed": 0})  # type: ignore[method-assign]

    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc.run_suite(layers=["pytest", "infra"])

    assert len(result["layers"]) == 2
    layer_names = [lr["name"] for lr in result["layers"]]
    assert "pytest" in layer_names
    assert "infra" in layer_names
    assert "smoke" not in layer_names
    assert "tsc" not in layer_names


def test_qa_suite_run_suite_overall_failed_when_layer_fails(tmp_path: Path) -> None:
    svc = QASuiteService()

    svc._run_pytest = MagicMock(return_value={"name": "pytest", "status": "failed", "duration_ms": 1, "passed": 0, "failed": 2})  # type: ignore[method-assign]
    svc._run_smoke = MagicMock(return_value={"name": "smoke", "status": "passed", "duration_ms": 1, "passed": 3, "failed": 0})  # type: ignore[method-assign]
    svc._run_tsc = MagicMock(return_value={"name": "tsc", "status": "passed", "duration_ms": 1, "passed": 1, "failed": 0})  # type: ignore[method-assign]
    svc._run_infra = MagicMock(return_value={"name": "infra", "status": "passed", "duration_ms": 1, "passed": 4, "failed": 0})  # type: ignore[method-assign]

    with patch.object(type(svc.settings), "storage_root", new_callable=lambda: property(lambda s: tmp_path)):
        result = svc.run_suite()

    assert result["overall_status"] == "failed"
