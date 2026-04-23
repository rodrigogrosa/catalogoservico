from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.checksum_service import ChecksumService
from app.services.storage_service import StorageService


class ManifestService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = StorageService()
        self.checksum = ChecksumService()

    def build_manifest(
        self,
        manifest: dict[str, Any],
        original_files: list[Path],
        artifacts: list[dict[str, Any]],
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        created_at = manifest.get("created_at") or datetime.now(tz=timezone.utc).isoformat()
        return {
            "project_id": manifest["id"],
            "project_name": manifest["name"],
            "slug": manifest["slug"],
            "version": manifest["version"],
            "created_at": created_at,
            "updated_at": manifest.get("updated_at", created_at),
            "origin": manifest.get("original_filename"),
            "source_ecosystem": manifest.get("source_ecosystem", "generic"),
            "input_formats": sorted({Path(file_path).suffix.lower().lstrip(".") for file_path in original_files}),
            "pipeline_version": self.settings.pipeline_version,
            "agent_versions": {
                "orchestrator": self.settings.pipeline_version,
                "geometry_agent": self.settings.pipeline_version,
                "snapmaker_agent": self.settings.pipeline_version,
                "bambu_agent": self.settings.pipeline_version,
                "materials_agent": self.settings.pipeline_version,
                "colors_agent": self.settings.pipeline_version,
                "qa_agent": self.settings.pipeline_version,
            },
            "original_files": [
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "sha256": self.checksum.sha256(file_path),
                    "size_bytes": file_path.stat().st_size,
                }
                for file_path in original_files
                if file_path.exists()
            ],
            "artifacts": artifacts,
            "parameters": manifest.get("metadata", {}).get("request_parameters", {}),
            "automatic_decisions": manifest.get("metadata", {}).get("decision_log", []),
            "questions_asked": manifest.get("questions_pending", []),
            "user_answers": manifest.get("metadata", {}).get("user_answers", []),
            "limitations": manifest.get("metadata", {}).get("limitations", []),
            "snapshot": snapshot or manifest.get("metadata", {}).get("execution_snapshot", {}),
        }

    def write_manifest(self, project_root: Path, payload: dict[str, Any]) -> Path:
        path = project_root / "project_manifest.json"
        self.storage.write_json(path, payload)
        return path
