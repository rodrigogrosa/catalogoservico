"""Lightweight project index backed by SQLite (local dev) or PostgreSQL (Northflank).

Uses SQLAlchemy Core – no ORM, no Alembic.  Schema is bootstrapped with
``CREATE TABLE IF NOT EXISTS`` on first use so there is nothing to migrate.

Environment:
    DATABASE_URL   – optional. If present (Northflank injects it automatically
                     for the PostgreSQL addon), it is used instead of SQLite.
                     Both ``postgres://`` and ``postgresql://`` schemes are
                     accepted; the former is normalised automatically.

Design:
    Only *summary* fields are stored in the DB (the same fields returned by
    ``StorageService.build_project_summary``).  Full manifests continue to
    live on the filesystem; the DB provides O(1) lookup of storage_path and
    fast sorted listings without scanning the network volume.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_db_url(url: str) -> str:
    """Northflank supplies ``postgres://`` which SQLAlchemy no longer accepts."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _make_engine(url: str) -> Any:
    from sqlalchemy import create_engine  # deferred – avoids import cost if unused

    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if not url.startswith("postgresql"):
        # SQLite: only one thread at a time by default – relax that so the
        # FastAPI threadpool can share the same connection pool.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id               TEXT    PRIMARY KEY,
    slug             TEXT    NOT NULL,
    name             TEXT,
    version          INTEGER NOT NULL DEFAULT 1,
    status           TEXT    NOT NULL DEFAULT 'pending',
    input_format     TEXT,
    source_ecosystem TEXT,
    storage_path     TEXT    NOT NULL,
    preview_url      TEXT,
    printable_score  TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
)
"""

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects (updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_projects_slug       ON projects (slug)",
]


def _bootstrap_schema(engine: Any) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(_SCHEMA_DDL))
        for stmt in _INDEX_DDL:
            conn.execute(text(stmt))


# ---------------------------------------------------------------------------
# Short alias used throughout
# ---------------------------------------------------------------------------


def _t(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DatabaseService:
    """Thread-safe project index.  Falls back gracefully if unavailable."""

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self._engine: Any = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_url(self) -> str:
        raw = os.environ.get("DATABASE_URL", "").strip()
        if raw:
            return _normalise_db_url(raw)
        # Local SQLite next to the storage root
        db_path = self.storage_root / "_system" / "app.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        with _lock:
            if self._engine is not None:
                return self._engine
            try:
                url = self._resolve_url()
                engine = _make_engine(url)
                _bootstrap_schema(engine)
                self._engine = engine
                logger.info("db_ready", extra={"driver": url.split("://")[0]})
            except Exception:
                logger.exception("db_init_failed")
                self._engine = None
        return self._engine

    # ------------------------------------------------------------------
    # Lifecycle queries
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._get_engine() is not None

    def has_any_projects(self) -> bool:
        """Return True if the ``projects`` table contains at least one row."""
        engine = self._get_engine()
        if engine is None:
            return False
        try:
            with engine.connect() as conn:
                row = conn.execute(_t("SELECT COUNT(*) FROM projects")).fetchone()
            return bool(row and row[0] > 0)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def upsert_project(self, manifest: dict[str, Any]) -> None:
        engine = self._get_engine()
        if engine is None:
            return
        project_id = manifest.get("id")
        if not project_id:
            return
        ps = manifest.get("printable_score")
        try:
            row: dict[str, Any] = {
                "id": project_id,
                "slug": manifest.get("slug") or "",
                "name": manifest.get("name"),
                "version": int(manifest.get("version") or 1),
                "status": manifest.get("status") or "pending",
                "input_format": manifest.get("input_format"),
                "source_ecosystem": manifest.get("source_ecosystem"),
                "storage_path": str(manifest.get("storage_path") or ""),
                "preview_url": manifest.get("preview_url"),
                "printable_score": json.dumps(ps) if isinstance(ps, dict) else None,
                "created_at": str(manifest.get("created_at") or ""),
                "updated_at": str(manifest.get("updated_at") or ""),
            }
            url_str = str(engine.url)
            with engine.begin() as conn:
                if "postgresql" in url_str:
                    conn.execute(
                        _t("""
                            INSERT INTO projects
                                (id, slug, name, version, status, input_format,
                                 source_ecosystem, storage_path, preview_url,
                                 printable_score, created_at, updated_at)
                            VALUES
                                (:id, :slug, :name, :version, :status, :input_format,
                                 :source_ecosystem, :storage_path, :preview_url,
                                 :printable_score, :created_at, :updated_at)
                            ON CONFLICT (id) DO UPDATE SET
                                name             = EXCLUDED.name,
                                version          = EXCLUDED.version,
                                status           = EXCLUDED.status,
                                input_format     = EXCLUDED.input_format,
                                source_ecosystem = EXCLUDED.source_ecosystem,
                                storage_path     = EXCLUDED.storage_path,
                                preview_url      = EXCLUDED.preview_url,
                                printable_score  = EXCLUDED.printable_score,
                                updated_at       = EXCLUDED.updated_at
                        """),
                        row,
                    )
                else:
                    conn.execute(
                        _t("""
                            INSERT OR REPLACE INTO projects
                                (id, slug, name, version, status, input_format,
                                 source_ecosystem, storage_path, preview_url,
                                 printable_score, created_at, updated_at)
                            VALUES
                                (:id, :slug, :name, :version, :status, :input_format,
                                 :source_ecosystem, :storage_path, :preview_url,
                                 :printable_score, :created_at, :updated_at)
                        """),
                        row,
                    )
        except Exception:
            logger.exception("db_upsert_failed", extra={"project_id": project_id})

    def delete_project(self, project_id: str) -> None:
        engine = self._get_engine()
        if engine is None:
            return
        try:
            with engine.begin() as conn:
                conn.execute(_t("DELETE FROM projects WHERE id = :id"), {"id": project_id})
        except Exception:
            logger.exception("db_delete_failed", extra={"project_id": project_id})

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_latest_projects(self) -> list[dict[str, Any]]:
        """Return one row per slug (the highest version), sorted by updated_at DESC."""
        engine = self._get_engine()
        if engine is None:
            return []
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    _t("""
                        SELECT id, slug, name, version, status, input_format,
                               source_ecosystem, storage_path, preview_url,
                               printable_score, created_at, updated_at
                        FROM   projects p
                        WHERE  version = (
                            SELECT MAX(p2.version)
                            FROM   projects p2
                            WHERE  p2.slug = p.slug
                        )
                        ORDER  BY updated_at DESC
                    """)
                )
                rows = result.fetchall()
                keys = list(result.keys())
            return [self._decode_row(dict(zip(keys, r))) for r in rows]
        except Exception:
            logger.exception("db_list_latest_failed")
            return []

    def find_storage_path(self, project_id: str) -> str | None:
        """O(1) lookup – avoids filesystem glob on every project detail request."""
        engine = self._get_engine()
        if engine is None:
            return None
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    _t("SELECT storage_path FROM projects WHERE id = :id"),
                    {"id": project_id},
                ).fetchone()
            return row[0] if row else None
        except Exception:
            logger.exception("db_find_storage_path_failed", extra={"project_id": project_id})
            return None

    def list_versions(self, slug: str) -> list[dict[str, Any]]:
        """All versions for a slug, newest first."""
        engine = self._get_engine()
        if engine is None:
            return []
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    _t("""
                        SELECT id, slug, name, version, status, input_format,
                               source_ecosystem, storage_path, preview_url,
                               printable_score, created_at, updated_at
                        FROM   projects
                        WHERE  slug = :slug
                        ORDER  BY version DESC
                    """),
                    {"slug": slug},
                )
                rows = result.fetchall()
                keys = list(result.keys())
            return [self._decode_row(dict(zip(keys, r))) for r in rows]
        except Exception:
            logger.exception("db_list_versions_failed", extra={"slug": slug})
            return []

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def sync_from_filesystem(self, storage_root: Path) -> int:
        """Bootstrap the DB from existing on-disk manifests.  Returns synced count."""
        count = 0
        for project_dir in storage_root.glob("*/*"):
            if not project_dir.is_dir():
                continue
            manifest_file = project_dir / "project.json"
            if not manifest_file.exists():
                continue
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest["storage_path"] = str(project_dir)
                self.upsert_project(manifest)
                count += 1
            except Exception:
                logger.exception("db_sync_manifest_failed", extra={"path": str(manifest_file)})
        logger.info("db_sync_completed", extra={"count": count})
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_row(item: dict[str, Any]) -> dict[str, Any]:
        if item.get("printable_score"):
            try:
                item["printable_score"] = json.loads(item["printable_score"])
            except Exception:
                item["printable_score"] = None
        item.setdefault("sales_profile", None)
        return item
