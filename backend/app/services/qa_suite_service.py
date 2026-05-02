"""Agente de Testes — executa todas as camadas de teste do projeto:

  Camada 1  — Backend pytest (backend/tests/)
  Camada 2  — API smoke (health + auth endpoints via httpx)
  Camada 3  — Frontend TypeScript check (tsc --noEmit)
  Camada 4  — Infra checks (storage acessível, Ollama acessível)

Pode ser chamado de forma síncrona (run_suite) ou via SSE (stream_run) para
feedback em tempo real. O último resultado é persistido em
_system/qa_suite_result.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_DIR = "_system"
_QA_FILE = "qa_suite_result.json"

# timeouts (seconds)
_PYTEST_TIMEOUT = 180
_TSC_TIMEOUT = 90
_SMOKE_TIMEOUT = 30
_INFRA_TIMEOUT = 10

# Locate workspace root (SupeRAG & Scaffold / SnapMaker3d Studio /)
_HERE = Path(__file__).resolve()
_WORKSPACE_ROOT = _HERE.parents[4]  # backend/app/services/ → workspace root

# ── Module-level state so SSE can read live output ──────────────────────────
_current_run: dict[str, Any] = {}
_run_lines: list[str] = []


def get_current_run() -> dict[str, Any]:
    return _current_run


def get_run_lines() -> list[str]:
    return list(_run_lines)


class QASuiteService:
    """Runs all test layers and returns structured results."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._workspace_root = _WORKSPACE_ROOT

    # ── Public API ────────────────────────────────────────────────────────

    def get_last_result(self) -> dict[str, Any]:
        """Return the persisted result of the last QA run, or a placeholder."""
        path = self._result_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"status": "never_run", "layers": [], "overall_status": "never_run", "total_duration_ms": 0}

    def run_suite(self, layers: list[str] | None = None) -> dict[str, Any]:
        """
        Execute all (or selected) test layers synchronously.
        layers: subset from ["pytest", "smoke", "tsc", "infra"] — None = all
        """
        global _current_run, _run_lines
        _current_run = {"status": "running", "started_at": datetime.now(tz=timezone.utc).isoformat()}
        _run_lines = []

        run_layers = set(layers) if layers else {"pytest", "smoke", "tsc", "infra"}
        started = time.monotonic()
        layer_results: list[dict[str, Any]] = []

        if "pytest" in run_layers:
            layer_results.append(self._run_pytest())
        if "smoke" in run_layers:
            layer_results.append(self._run_smoke())
        if "tsc" in run_layers:
            layer_results.append(self._run_tsc())
        if "infra" in run_layers:
            layer_results.append(self._run_infra())

        total_ms = int((time.monotonic() - started) * 1000)
        failed_layers = [lr for lr in layer_results if lr["status"] in ("failed", "error")]
        overall = "passed" if not failed_layers else "failed"

        result: dict[str, Any] = {
            "started_at": _current_run["started_at"],
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
            "overall_status": overall,
            "total_duration_ms": total_ms,
            "layers": layer_results,
        }
        _current_run = {**result, "status": "done"}
        self._persist_result(result)
        logger.info("qa_suite_done", extra={"overall": overall, "total_ms": total_ms})
        return result

    async def stream_run(self, layers: list[str] | None = None) -> AsyncIterator[str]:
        """
        Run the suite in a thread and yield SSE data lines with live progress.
        Each yielded string is already formatted as 'data: {...}\\n\\n'.
        """
        global _current_run, _run_lines
        _current_run = {"status": "running", "started_at": datetime.now(tz=timezone.utc).isoformat()}
        _run_lines = []

        loop = asyncio.get_event_loop()

        # Start suite in background thread
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = loop.run_in_executor(executor, self.run_suite, layers)

        last_line_count = 0
        while not future.done():
            await asyncio.sleep(0.3)
            current_lines = _run_lines[last_line_count:]
            if current_lines:
                for line in current_lines:
                    yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"
                last_line_count = len(_run_lines)
            yield f"data: {json.dumps({'type': 'ping', 'status': 'running'})}\n\n"

        result = await future
        yield f"data: {json.dumps({'type': 'done', 'result': result})}\n\n"

    # ── Layer 1: pytest ───────────────────────────────────────────────────

    def _run_pytest(self) -> dict[str, Any]:
        name = "pytest"
        started = time.monotonic()
        _run_lines.append(f"[pytest] Iniciando pytest em backend/tests/ ...")
        try:
            tests_dir = self._workspace_root / "backend" / "tests"
            backend_dir = self._workspace_root / "backend"
            env = {**os.environ, "PYTHONPATH": str(backend_dir), "PYTHONDONTWRITEBYTECODE": "1"}
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=short", "-q", "--no-header"],
                capture_output=True,
                text=True,
                timeout=_PYTEST_TIMEOUT,
                cwd=str(backend_dir),
                env=env,
            )
            output = proc.stdout + proc.stderr
            for line in output.splitlines()[-30:]:
                _run_lines.append(f"[pytest] {line}")

            passed = failed = errors = 0
            for line in output.splitlines():
                m = __import__("re").search(r"(\d+) passed", line)
                if m:
                    passed = int(m.group(1))
                m = __import__("re").search(r"(\d+) failed", line)
                if m:
                    failed = int(m.group(1))
                m = __import__("re").search(r"(\d+) error", line)
                if m:
                    errors = int(m.group(1))

            status = "passed" if proc.returncode == 0 else "failed"
            return self._layer_result(name, status, started, passed, failed + errors, output=output[-4000:])
        except subprocess.TimeoutExpired:
            _run_lines.append(f"[pytest] TIMEOUT ({_PYTEST_TIMEOUT}s)")
            return self._layer_result(name, "error", started, error=f"Timeout ({_PYTEST_TIMEOUT}s)")
        except Exception as exc:  # noqa: BLE001
            _run_lines.append(f"[pytest] ERROR: {exc}")
            return self._layer_result(name, "error", started, error=str(exc))

    # ── Layer 2: API smoke ────────────────────────────────────────────────

    def _run_smoke(self) -> dict[str, Any]:
        name = "smoke"
        started = time.monotonic()
        _run_lines.append("[smoke] Iniciando API smoke test ...")
        checks: list[dict[str, Any]] = []
        try:
            import httpx
            base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
            client = httpx.Client(base_url=base_url, timeout=_SMOKE_TIMEOUT)

            def check(label: str, method: str, path: str, *, expected: int = 200, **kwargs: Any) -> bool:
                try:
                    resp = getattr(client, method)(path, **kwargs)
                    ok = resp.status_code == expected
                    checks.append({"label": label, "status_code": resp.status_code, "ok": ok})
                    _run_lines.append(f"[smoke] {label}: HTTP {resp.status_code} {'✓' if ok else '✗'}")
                    return ok
                except Exception as exc:  # noqa: BLE001
                    checks.append({"label": label, "error": str(exc), "ok": False})
                    _run_lines.append(f"[smoke] {label}: ERROR {exc}")
                    return False

            check("GET /api/v1/health", "get", "/api/v1/health")
            check("GET /api/v1/health/ready", "get", "/api/v1/health/ready")
            check("GET /api/v1/projects (sem token)", "get", "/api/v1/projects", expected=401)

            # Try login with a known test credential (gracefully skipped if not available)
            test_email = os.getenv("TEST_USER_EMAIL", "")
            test_pass = os.getenv("TEST_USER_PASSWORD", "")
            if test_email and test_pass:
                try:
                    login_resp = client.post(
                        "/api/v1/auth/login",
                        json={"email": test_email, "password": test_pass},
                    )
                    if login_resp.status_code == 200:
                        token = login_resp.json().get("token", "")
                        headers = {"Authorization": f"Bearer {token}"}
                        check("GET /api/v1/projects (com token)", "get", "/api/v1/projects", headers=headers)
                        check("GET /api/v1/catalog", "get", "/api/v1/catalog", headers=headers)
                        checks.append({"label": "login", "status_code": 200, "ok": True})
                    else:
                        checks.append({"label": "login", "status_code": login_resp.status_code, "ok": False})
                except Exception as exc:  # noqa: BLE001
                    checks.append({"label": "login", "error": str(exc), "ok": False})

            passed = sum(1 for c in checks if c.get("ok"))
            failed = len(checks) - passed
            status = "passed" if failed == 0 else "failed"
            return self._layer_result(name, status, started, passed=passed, failed=failed, extra={"checks": checks})
        except ImportError:
            msg = "httpx não disponível para smoke test"
            _run_lines.append(f"[smoke] SKIP: {msg}")
            return self._layer_result(name, "skipped", started, error=msg)
        except Exception as exc:  # noqa: BLE001
            _run_lines.append(f"[smoke] ERROR: {exc}")
            return self._layer_result(name, "error", started, error=str(exc))

    # ── Layer 3: TypeScript check ─────────────────────────────────────────

    def _run_tsc(self) -> dict[str, Any]:
        name = "tsc"
        started = time.monotonic()
        _run_lines.append("[tsc] Verificando TypeScript (tsc --noEmit) ...")
        frontend_dir = self._workspace_root / "frontend"
        if not frontend_dir.exists():
            _run_lines.append("[tsc] SKIP: diretório frontend não encontrado")
            return self._layer_result(name, "skipped", started, error="frontend/ não encontrado")
        try:
            proc = subprocess.run(
                ["npx", "--yes", "tsc", "--noEmit"],
                capture_output=True,
                text=True,
                timeout=_TSC_TIMEOUT,
                cwd=str(frontend_dir),
            )
            output = proc.stdout + proc.stderr
            for line in output.splitlines()[-20:]:
                _run_lines.append(f"[tsc] {line}")

            error_count = output.count("error TS")
            status = "passed" if proc.returncode == 0 else "failed"
            return self._layer_result(name, status, started, passed=0 if status == "failed" else 1, failed=error_count, output=output[-2000:])
        except subprocess.TimeoutExpired:
            _run_lines.append(f"[tsc] TIMEOUT ({_TSC_TIMEOUT}s)")
            return self._layer_result(name, "error", started, error=f"Timeout ({_TSC_TIMEOUT}s)")
        except FileNotFoundError:
            msg = "npx não encontrado. Verifique se Node.js está instalado."
            _run_lines.append(f"[tsc] SKIP: {msg}")
            return self._layer_result(name, "skipped", started, error=msg)
        except Exception as exc:  # noqa: BLE001
            _run_lines.append(f"[tsc] ERROR: {exc}")
            return self._layer_result(name, "error", started, error=str(exc))

    # ── Layer 4: Infra checks ─────────────────────────────────────────────

    def _run_infra(self) -> dict[str, Any]:
        name = "infra"
        started = time.monotonic()
        _run_lines.append("[infra] Verificando infraestrutura ...")
        checks: list[dict[str, Any]] = []

        # Storage root accessible?
        storage_ok = self.settings.storage_root.exists()
        checks.append({"label": "storage_root_exists", "ok": storage_ok})
        _run_lines.append(f"[infra] storage_root ({self.settings.storage_root}): {'✓' if storage_ok else '✗'}")

        # Storage writable?
        storage_write_ok = False
        if storage_ok:
            test_file = self.settings.storage_root / ".qa_write_test"
            try:
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink(missing_ok=True)
                storage_write_ok = True
            except Exception:
                pass
        checks.append({"label": "storage_writable", "ok": storage_write_ok})
        _run_lines.append(f"[infra] storage_writable: {'✓' if storage_write_ok else '✗'}")

        # Ollama reachable?
        ollama_ok = False
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/tags", timeout=_INFRA_TIMEOUT)
            ollama_ok = resp.status_code == 200
        except Exception:
            pass
        checks.append({"label": "ollama_reachable", "ok": ollama_ok})
        _run_lines.append(f"[infra] ollama_reachable: {'✓' if ollama_ok else '✗ (opcional)'}")

        # Backend API reachable?
        backend_ok = False
        try:
            import httpx
            resp = httpx.get("http://localhost:8000/api/v1/health", timeout=_INFRA_TIMEOUT)
            backend_ok = resp.status_code == 200
        except Exception:
            pass
        checks.append({"label": "backend_api_health", "ok": backend_ok})
        _run_lines.append(f"[infra] backend_api_health: {'✓' if backend_ok else '✗'}")

        # Critical checks: storage must be ok
        critical_failed = [c for c in checks[:2] if not c["ok"]]
        status = "failed" if critical_failed else "passed"
        passed = sum(1 for c in checks if c.get("ok"))
        return self._layer_result(name, status, started, passed=passed, failed=len(checks) - passed, extra={"checks": checks})

    # ── Helpers ───────────────────────────────────────────────────────────

    def _layer_result(
        self,
        name: str,
        status: str,
        started: float,
        passed: int = 0,
        failed: int = 0,
        error: str | None = None,
        output: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        duration_ms = int((time.monotonic() - started) * 1000)
        result: dict[str, Any] = {
            "name": name,
            "status": status,
            "duration_ms": duration_ms,
            "passed": passed,
            "failed": failed,
        }
        if error:
            result["error"] = error
        if output:
            result["output"] = output
        if extra:
            result.update(extra)
        return result

    def _result_path(self) -> Path:
        system_dir = self.settings.storage_root / _SYSTEM_DIR
        system_dir.mkdir(parents=True, exist_ok=True)
        return system_dir / _QA_FILE

    def _persist_result(self, result: dict[str, Any]) -> None:
        try:
            self._result_path().write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("qa_suite_persist_failed", extra={"error": str(exc)})
