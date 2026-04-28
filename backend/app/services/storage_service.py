from __future__ import annotations

import asyncio
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
from app.services.database_service import DatabaseService


logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.root = self.settings.storage_root
        self.upload_chunk_size_bytes = 1024 * 1024
        self.db = DatabaseService(self.root)
        # Populate the DB index from disk on first start if it is empty.
        # This is a cheap O(N) scan that only runs once per process lifetime.
        if self.db.available and not self.db.has_any_projects():
            try:
                self.db.sync_from_filesystem(self.root)
            except Exception:
                logger.exception("storage_db_initial_sync_failed")

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
        return await asyncio.to_thread(self.save_upload_sync, upload, target_dir)

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
        return await asyncio.to_thread(self.save_uploads_sync, uploads, target_dir)

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
        # FileNotFoundError: não há retry — o arquivo não existe
        # JSONDecodeError: pode ser race condition de escrita; retry até 3x com backoff curto
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.02 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def manifest_path(self, project_root: Path) -> Path:
        return project_root / "project.json"

    def summary_path(self, project_root: Path) -> Path:
        return project_root / "project.summary.json"

    def to_storage_url(self, path: Path | str) -> str:
        file_path = Path(path)
        relative = file_path.relative_to(self.root)
        return f"/storage/{relative.as_posix()}"

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        project_root = Path(manifest["storage_path"])
        self.write_json(self.manifest_path(project_root), manifest)
        self.write_json(self.summary_path(project_root), self.build_project_summary(manifest))
        self.db.upsert_project(manifest)

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
        # Fast path: DB tells us exactly where the directory is.
        storage_path = self.db.find_storage_path(project_id)
        if storage_path:
            project_dir = Path(storage_path)
            manifest_file = project_dir / "project.json"
            if manifest_file.exists():
                return self.normalize_manifest_paths(self.read_json(manifest_file), project_dir)
        # Slow path: filesystem glob (used when DB is unavailable or not yet synced).
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
            self.db.delete_project(project_id)
            return True
        return False

    def list_manifests(self) -> list[dict[str, Any]]:
        # Fast path: use the DB index (returns only the latest version per slug).
        if self.db.available and self.db.has_any_projects():
            return self.db.list_latest_projects()

        # Slow path: scan the filesystem and populate the DB for future calls.
        manifests: list[dict[str, Any]] = []
        for project_dir in self.root.glob("*/*"):
            if not project_dir.is_dir():
                continue
            summary_file = self.summary_path(project_dir)
            manifest_file = self.manifest_path(project_dir)
            source = summary_file if summary_file.exists() else manifest_file
            if not source.exists():
                continue
            try:
                payload = self.read_json(source)
                if source == manifest_file:
                    payload = self.build_project_summary(payload)
                    self.write_json(summary_file, payload)
                manifests.append(payload)
                # Back-fill the DB while we're here
                if self.db.available:
                    payload_with_path = dict(payload)
                    payload_with_path.setdefault("storage_path", str(project_dir))
                    self.db.upsert_project(payload_with_path)
            except Exception:
                logger.exception(
                    "manifest_load_failed",
                    extra={
                        "manifest_path": str(source),
                        "project_root": str(project_dir),
                    },
                )
                continue

        # Return only the latest version per slug (mirrors the DB behaviour).
        by_slug: dict[str, dict[str, Any]] = {}
        for item in manifests:
            slug = item.get("slug")
            if not slug:
                continue
            existing = by_slug.get(slug)
            if existing is None or int(item.get("version") or 0) > int(existing.get("version") or 0):
                by_slug[slug] = item
        return sorted(by_slug.values(), key=lambda x: str(x.get("updated_at", "")), reverse=True)

    def build_project_summary(self, manifest: dict[str, Any]) -> dict[str, Any]:
        printable_score = manifest.get("printable_score")
        if not isinstance(printable_score, dict):
            printable_score = None
        summary = {
            "id": manifest.get("id"),
            "name": manifest.get("name"),
            "slug": manifest.get("slug"),
            "version": manifest.get("version"),
            "status": manifest.get("status"),
            "input_format": manifest.get("input_format"),
            "source_ecosystem": manifest.get("source_ecosystem"),
            "created_at": manifest.get("created_at"),
            "updated_at": manifest.get("updated_at"),
            "preview_url": manifest.get("preview_url"),
            "printable_score": printable_score,
            "sales_profile": None,
        }
        return summary

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

    # ------------------------------------------------------------------
    # Version helpers
    # ------------------------------------------------------------------

    def list_versions_for_slug(self, slug: str) -> list[dict[str, Any]]:
        """Return all stored versions for *slug*, newest first."""
        if self.db.available:
            return self.db.list_versions(slug)
        # Filesystem fallback
        slug_dir = self.root / slug
        if not slug_dir.exists():
            return []
        versions: list[dict[str, Any]] = []
        for project_dir in slug_dir.iterdir():
            if not project_dir.is_dir():
                continue
            source = self.summary_path(project_dir)
            if not source.exists():
                source = self.manifest_path(project_dir)
            if not source.exists():
                continue
            try:
                payload = self.read_json(source)
                if source == self.manifest_path(project_dir):
                    payload = self.build_project_summary(payload)
                versions.append(payload)
            except Exception:
                continue
        versions.sort(key=lambda x: int(x.get("version") or 0), reverse=True)
        return versions

    def create_reprocess_version(self, source_manifest: dict[str, Any]) -> dict[str, Any]:
        """Create a new version directory by copying the original files.

        Returns the same ``layout`` dict as ``create_project_layout`` so the
        caller can build a fresh manifest and start the pipeline.
        """
        slug = source_manifest["slug"]
        version = self.next_version(slug)
        version_name = f"{slug}_v{version:03d}"
        project_root = self.root / slug / version_name
        folders: dict[str, Path] = {
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

        # Copy original source files so the user doesn't need to re-upload.
        source_original = Path(source_manifest["storage_path"]) / "original"
        if source_original.exists():
            for file_path in source_original.iterdir():
                if file_path.is_file():
                    shutil.copy2(file_path, folders["original"] / file_path.name)

        return {
            "slug": slug,
            "version": version,
            "version_name": version_name,
            "folders": folders,
        }

