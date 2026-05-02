"""Super Revisor de Qualidade — analisa logs, manifests e código em busca de
padrões de erro, warning, performance e escalabilidade.

Roda em background a cada REVIEW_INTERVAL_SECONDS (padrão: 1800 = 30 min)
e também pode ser disparado manualmente via API.  O resultado é persistido em
_system/review_report.json dentro do storage root.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.free_ai_service import FreeAiService
from app.services.local_llm_service import LocalLlmService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REVIEW_INTERVAL_SECONDS = 1800  # 30 min
_SYSTEM_DIR = "_system"
_REVIEW_FILE = "review_report.json"
_MAX_LOG_LINES = 200          # lines sampled from each project log
_MAX_PROJECTS_SCAN = 20       # most-recent projects to include

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
REVIEWER_SYSTEM_PROMPT = """\
Você é um engenheiro de software sênior com foco em qualidade, performance,
escalabilidade e segurança de APIs FastAPI (Python 3.13) e Next.js 15.

Analise os dados de observabilidade fornecidos e retorne SOMENTE JSON válido
(sem markdown) com esta estrutura:
{
  "health_score": <int 0-100>,
  "summary": "<string 2-3 frases>",
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "error|performance|scalability|test|quality|security",
      "title": "<string curta>",
      "detail": "<string explicativa>",
      "suggestion": "<string acionável>",
      "source": "<log_file|project_id|system>"
    }
  ],
  "priority_actions": ["<ação 1>", "<ação 2>", "<ação 3>"],
  "auto_fixes_applied": ["<descrição da correção automática aplicada>"]
}
Seja objetivo e direto. Priorize issues que impactam usuários ou dados em produção.
"""


class ReviewerService:
    """Agente revisor autônomo de qualidade e saúde do sistema."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = LocalLlmService(self.settings)
        self.free_ai = FreeAiService(self.settings, llm_service=self.llm)
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────

    def get_report(self) -> dict[str, Any]:
        """Return the persisted review report, or a placeholder if none exists."""
        path = self._report_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._empty_report("Nenhuma revisão executada ainda.")

    def run_review(self) -> dict[str, Any]:
        """Execute a full review synchronously and persist the result."""
        with self._lock:
            return self._do_review()

    def start_background_loop(self) -> None:
        """Launch a daemon thread that reviews the system every REVIEW_INTERVAL_SECONDS."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="reviewer-agent",
        )
        self._thread.start()
        logger.info("reviewer_agent_started", extra={"interval_s": REVIEW_INTERVAL_SECONDS})

    def stop_background_loop(self) -> None:
        self._running = False

    # ── Internal ──────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                self._do_review()
            except Exception as exc:  # noqa: BLE001
                logger.warning("reviewer_loop_error", extra={"error": str(exc)})
            next_run = time.time() + REVIEW_INTERVAL_SECONDS
            while self._running and time.time() < next_run:
                time.sleep(10)

    def _do_review(self) -> dict[str, Any]:
        started_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("reviewer_run_started")

        raw_data = self._collect_observability_data()
        auto_fixes: list[str] = self._apply_auto_fixes(raw_data)

        ai_result, meta = self.free_ai.generate_json_with_fallback(
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "recent_errors": raw_data["errors"][:40],
                    "recent_warnings": raw_data["warnings"][:40],
                    "failed_projects": raw_data["failed_projects"],
                    "project_stats": raw_data["stats"],
                    "slow_endpoints": raw_data["slow_endpoints"],
                },
                ensure_ascii=False,
            ),
            fallback=self._deterministic_findings(raw_data),
        )

        report: dict[str, Any] = {
            "started_at": started_at,
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
            "provider": meta.get("selected_provider", "unknown"),
            "health_score": ai_result.get("health_score", 70),
            "summary": ai_result.get("summary", "Revisão concluída."),
            "findings": ai_result.get("findings", []),
            "priority_actions": ai_result.get("priority_actions", []),
            "auto_fixes_applied": auto_fixes + ai_result.get("auto_fixes_applied", []),
            "raw_stats": raw_data["stats"],
        }

        self._persist_report(report)
        logger.info(
            "reviewer_run_done",
            extra={
                "health_score": report["health_score"],
                "findings": len(report["findings"]),
                "provider": report["provider"],
            },
        )
        return report

    # ── Data collection ───────────────────────────────────────────────────

    def _collect_observability_data(self) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        failed_projects: list[dict[str, Any]] = []
        slow_endpoints: list[str] = []

        storage_root = self.settings.storage_root
        if not storage_root.exists():
            return {
                "errors": errors,
                "warnings": warnings,
                "failed_projects": failed_projects,
                "slow_endpoints": slow_endpoints,
                "stats": {"total_projects": 0, "failed": 0, "completed": 0, "processing": 0},
            }

        # ── Scan project manifests ──────────────────────────────────────
        manifests = sorted(
            storage_root.rglob("project.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:_MAX_PROJECTS_SCAN]

        total = completed = failed = processing = 0
        for manifest_path in manifests:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                total += 1
                status = manifest.get("status", "unknown")
                if status == "failed":
                    failed += 1
                    failed_projects.append(
                        {
                            "id": manifest.get("id", "?"),
                            "name": manifest.get("name", "?"),
                            "risks": manifest.get("risks", [])[:3],
                            "updated_at": manifest.get("updated_at", ""),
                        }
                    )
                elif status == "completed":
                    completed += 1
                elif status == "processing":
                    processing += 1

                # Check for error/warning patterns inside the manifest risks
                for risk in manifest.get("risks", []):
                    text = str(risk).strip()
                    if re.search(r"\b(erro|error|falha|exception|traceback)\b", text, re.IGNORECASE):
                        errors.append(f"[{manifest.get('id','?')}] {text[:160]}")
                    elif re.search(r"\b(aviso|warning|warn|atenção)\b", text, re.IGNORECASE):
                        warnings.append(f"[{manifest.get('id','?')}] {text[:160]}")
            except Exception:  # noqa: BLE001
                pass

        # ── Scan processing logs ────────────────────────────────────────
        log_files = sorted(
            storage_root.rglob("processing.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]

        for log_file in log_files:
            try:
                lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines[-_MAX_LOG_LINES:]:
                    if re.search(r"\bERROR\b|\bERRO\b|\bexception\b|\btraceback\b", line, re.IGNORECASE):
                        errors.append(f"[log:{log_file.parent.parent.name}] {line.strip()[:200]}")
                    elif re.search(r"\bWARNING\b|\bWARN\b|\baviso\b|\batenção\b", line, re.IGNORECASE):
                        warnings.append(f"[log:{log_file.parent.parent.name}] {line.strip()[:200]}")
                    elif re.search(r"duration.*\b(\d{4,})\s*ms", line, re.IGNORECASE):
                        slow_endpoints.append(line.strip()[:200])
            except Exception:  # noqa: BLE001
                pass

        return {
            "errors": list(dict.fromkeys(errors))[:60],
            "warnings": list(dict.fromkeys(warnings))[:60],
            "failed_projects": failed_projects[:10],
            "slow_endpoints": slow_endpoints[:20],
            "stats": {
                "total_projects": total,
                "failed": failed,
                "completed": completed,
                "processing": processing,
                "failure_rate_pct": round(failed / max(total, 1) * 100, 1),
            },
        }

    # ── Auto-fixes ────────────────────────────────────────────────────────

    def _apply_auto_fixes(self, raw_data: dict[str, Any]) -> list[str]:
        """Execute safe, reversible automatic fixes and return descriptions."""
        fixes: list[str] = []

        # Fix 1: generate sales_profile for failed projects that have completed versions nearby
        storage_root = self.settings.storage_root
        if not storage_root.exists():
            return fixes

        try:
            from app.services.sales_service import SalesService
            sales_service = SalesService()
            manifests = list(storage_root.rglob("project.json"))
            no_catalog = [
                m for m in manifests
                if not json.loads(m.read_text(encoding="utf-8")).get("sales_profile")
                and json.loads(m.read_text(encoding="utf-8")).get("status") == "completed"
            ][:5]
            for manifest_path in no_catalog:
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    profile = sales_service.build_sales_profile(manifest, allow_llm=False)
                    manifest["sales_profile"] = profile
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    fixes.append(f"Catálogo gerado automaticamente para '{manifest.get('name', manifest.get('id', '?'))}'.")
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

        return fixes

    # ── Deterministic fallback ────────────────────────────────────────────

    def _deterministic_findings(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        stats = raw_data["stats"]

        if stats.get("failure_rate_pct", 0) > 20:
            findings.append({
                "severity": "high",
                "category": "error",
                "title": f"Taxa de falha elevada: {stats['failure_rate_pct']}%",
                "detail": f"{stats['failed']} de {stats['total_projects']} projetos falharam.",
                "suggestion": "Revise os logs dos projetos com status 'failed' para identificar causa raiz.",
                "source": "system",
            })
        if raw_data["errors"]:
            findings.append({
                "severity": "high",
                "category": "error",
                "title": f"{len(raw_data['errors'])} erros encontrados nos logs",
                "detail": "; ".join(raw_data["errors"][:3]),
                "suggestion": "Revise os logs de processamento dos projetos afetados.",
                "source": "processing.log",
            })
        if raw_data["warnings"]:
            findings.append({
                "severity": "medium",
                "category": "quality",
                "title": f"{len(raw_data['warnings'])} avisos encontrados nos logs",
                "detail": "; ".join(raw_data["warnings"][:3]),
                "suggestion": "Analise os avisos para evitar que evoluam para erros.",
                "source": "processing.log",
            })
        if raw_data["slow_endpoints"]:
            findings.append({
                "severity": "medium",
                "category": "performance",
                "title": "Endpoints lentos detectados (>1000ms)",
                "detail": "; ".join(raw_data["slow_endpoints"][:2]),
                "suggestion": "Adicione cache Redis ou otimize consultas ao storage NFS.",
                "source": "processing.log",
            })

        health = max(0, 100 - len(raw_data["errors"]) * 5 - len(raw_data["warnings"]) * 2 - stats.get("failure_rate_pct", 0))
        return {
            "health_score": int(min(100, health)),
            "summary": f"Revisão determinística: {len(findings)} pontos identificados. Taxa de falha: {stats.get('failure_rate_pct', 0)}%.",
            "findings": findings,
            "priority_actions": [f["title"] for f in sorted(findings, key=lambda x: ["critical", "high", "medium", "low"].index(x["severity"]))[:3]],
            "auto_fixes_applied": [],
        }

    # ── Persistence ───────────────────────────────────────────────────────

    def _report_path(self) -> Path:
        system_dir = self.settings.storage_root / _SYSTEM_DIR
        system_dir.mkdir(parents=True, exist_ok=True)
        return system_dir / _REVIEW_FILE

    def _persist_report(self, report: dict[str, Any]) -> None:
        try:
            path = self._report_path()
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("reviewer_persist_failed", extra={"error": str(exc)})

    def _empty_report(self, reason: str) -> dict[str, Any]:
        return {
            "started_at": None,
            "completed_at": None,
            "provider": "none",
            "health_score": None,
            "summary": reason,
            "findings": [],
            "priority_actions": [],
            "auto_fixes_applied": [],
            "raw_stats": {},
        }
