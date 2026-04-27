from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any

from fastapi import UploadFile

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.root = self.settings.storage_root
        self.upload_chunk_size_bytes = 1024 * 1024

    def slugify(self, raw_name: str) -> str:
        value = raw_name.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = re.sub(r"-+", "-", value).strip("-")
        return value or "projeto-3d"

    def next_version(self, slug: str) -> int:
        project_root = self.root / slug
        if not project_root.exists():
            return 1
        versions = [
            int(match.group(1))
            for path in project_root.iterdir()
            if path.is_dir() and (match := re.search(r"_v(\d{3})$", path.name))
        ]
        return (max(versions) + 1) if versions else 1

    def create_project_layout(self, project_name: str) -> dict[str, Any]:
        slug = self.slugify(project_name)
        version = self.next_version(slug)
        version_name = f"{slug}_v{version:03d}"
        project_root = self.root / slug / version_name
        folders = {
            "root": project_root,
            "original": project_root / "original",
            "processed": project_root / "processado",
            "export": project_root / "export",
            "reports": project_root / "relatorios",
            "previews": project_root / "previews",
            "logs": project_root / "logs",
        }
        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)
        return {
            "slug": slug,
            "version": version,
            "version_name": version_name,
            "folders": folders,
        }

    def save_upload_sync(self, upload: UploadFile, target_dir: Path) -> Path:
        filename = Path(upload.filename or "arquivo-desconhecido").name
        if filename.lower().endswith(".slt"):
            filename = f"{Path(filename).stem}.stl"
        destination = self.unique_upload_path(target_dir / filename)
        written = 0
        upload.file.seek(0)
        with destination.open("wb") as buffer:
            while True:
                chunk = upload.file.read(self.upload_chunk_size_bytes)
                if not chunk:
                    break
                written += len(chunk)
                buffer.write(chunk)
        logger.info(
            "upload_saved_to_disk",
            extra={
                "upload_name": filename,
                "destination": str(destination),
                "size_bytes": written,
            },
        )
        return destination

    async def save_upload(self, upload: UploadFile, target_dir: Path) -> Path:
        return self.save_upload_sync(upload, target_dir)

    def unique_upload_path(self, destination: Path) -> Path:
        if not destination.exists():
            return destination
        stem = destination.stem
        suffix = destination.suffix
        return destination.parent / f"{stem}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}{suffix}"

    def save_uploads_sync(self, uploads: list[UploadFile], target_dir: Path) -> list[Path]:
        saved: list[Path] = []
        for upload in uploads:
            saved.append(self.save_upload_sync(upload, target_dir))
        return saved

    async def save_uploads(self, uploads: list[UploadFile], target_dir: Path) -> list[Path]:
        return self.save_uploads_sync(uploads, target_dir)

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, indent=2, ensure_ascii=False)
        temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}")
        temp_path.write_text(encoded, encoding="utf-8")
        os.replace(temp_path, path)

    def next_generated_file(self, target_dir: Path, stem: str, suffix: str) -> Path:
        final_candidate = target_dir / f"{stem}_final{suffix}"
        if not final_candidate.exists():
            return final_candidate

        index = 1
        while True:
            candidate = target_dir / f"{stem}_{index:02d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def read_json(self, path: Path) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(4):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(0.05)
        assert last_error is not None
        raise last_error

    def manifest_path(self, project_root: Path) -> Path:
        return project_root / "project.json"

    def to_storage_url(self, path: Path | str) -> str:
        file_path = Path(path)
        relative = file_path.relative_to(self.root)
        return f"/storage/{relative.as_posix()}"

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        path = Path(manifest["storage_path"]) / "project.json"
        self.write_json(path, manifest)

    def save_project_manifest(self, project_root: Path, payload: dict[str, Any]) -> None:
        self.write_json(project_root / "project_manifest.json", payload)

    def _safe_project_id(self, project_id: str) -> str:
        """Rejeita qualquer project_id que contenha componentes de path traversal."""
        sanitized = Path(project_id).name  # descarta qualquer prefixo de diretório
        if sanitized != project_id or ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError(f"project_id inválido: {project_id!r}")
        return sanitized

    def load_manifest(self, project_id: str) -> dict[str, Any] | None:
        project_id = self._safe_project_id(project_id)
        for project_dir in self.root.glob(f"*/{project_id}"):
            manifest = project_dir / "project.json"
            if manifest.exists():
                return self.normalize_manifest_paths(self.read_json(manifest), project_dir)
        return None

    def delete_project(self, project_id: str) -> bool:
        project_id = self._safe_project_id(project_id)
        for project_dir in self.root.glob(f"*/{project_id}"):
            if not project_dir.is_dir():
                continue
            project_dir.relative_to(self.root)
            parent_dir = project_dir.parent
            shutil.rmtree(project_dir)
            if parent_dir != self.root and parent_dir.exists() and not any(parent_dir.iterdir()):
                parent_dir.rmdir()
            return True
        return False

    def list_manifests(self) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        for manifest in self.root.glob("*/*/project.json"):
            try:
                manifests.append(self.normalize_manifest_paths(self.read_json(manifest), manifest.parent))
            except Exception as exc:
                logger.exception(
                    "manifest_load_failed",
                    extra={
                        "manifest_path": str(manifest),
                        "project_root": str(manifest.parent),
                    },
                )
                continue
        manifests.sort(key=lambda item: item["updated_at"], reverse=True)
        return manifests

    def normalize_manifest_paths(self, manifest: dict[str, Any], project_root: Path) -> dict[str, Any]:
        manifest["storage_path"] = str(project_root)
        known_dirs = {
            "original": project_root / "original",
            "processado": project_root / "processado",
            "processed": project_root / "processado",
            "export": project_root / "export",
            "previews": project_root / "previews",
            "relatorios": project_root / "relatorios",
            "reports": project_root / "relatorios",
            "logs": project_root / "logs",
        }
        for item in manifest.get("input_files", []):
            path = Path(str(item.get("path", "")))
            if path.exists():
                continue
            replacement = known_dirs["original"] / path.name
            if replacement.exists():
                item["path"] = str(replacement)
        return manifest
