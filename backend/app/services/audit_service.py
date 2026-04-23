from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from app.services.storage_service import StorageService


@dataclass
class AuditTimer:
    started_at_iso: str
    started_perf: float


class AuditService:
    def __init__(self) -> None:
        self.storage = StorageService()

    def start_timer(self) -> AuditTimer:
        return AuditTimer(
            started_at_iso=datetime.now(tz=timezone.utc).isoformat(),
            started_perf=perf_counter(),
        )

    def finish_metric(
        self,
        timer: AuditTimer,
        stage_key: str,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "stage_key": stage_key,
            "status": status,
            "started_at": timer.started_at_iso,
            "finished_at": datetime.now(tz=timezone.utc).isoformat(),
            "duration_ms": round((perf_counter() - timer.started_perf) * 1000, 2),
        }
        if extra:
            payload.update(extra)
        return payload

    def write_snapshot(self, reports_dir: Path, payload: dict[str, Any]) -> dict[str, str]:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        path = reports_dir / f"execution_snapshot_{timestamp}.json"
        self.storage.write_json(path, payload)
        return {
            "label": "Execution snapshot",
            "path": self.storage.to_storage_url(path),
            "kind": "snapshot",
        }

    def append_structured_log(self, logs_dir: Path, event: dict[str, Any]) -> str:
        path = logs_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return self.storage.to_storage_url(path)
