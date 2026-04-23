from __future__ import annotations

from pathlib import Path
import zipfile

from app.services.storage_service import StorageService


class BundleService:
    def __init__(self) -> None:
        self.storage = StorageService()

    def build_project_bundle(self, project_root: Path) -> dict[str, str]:
        bundle_dir = project_root / "export"
        bundle_path = self.storage.next_generated_file(bundle_dir, f"{project_root.name}_bundle", ".zip")
        include_dirs = ["export", "relatorios", "previews", "logs"]

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            manifest = project_root / "project_manifest.json"
            if manifest.exists():
                archive.write(manifest, arcname=manifest.name)
            for relative in include_dirs:
                folder = project_root / relative
                if not folder.exists():
                    continue
                for file_path in folder.rglob("*"):
                    if file_path.is_file():
                        archive.write(file_path, arcname=file_path.relative_to(project_root))

        return {
            "label": bundle_path.name,
            "path": self.storage.to_storage_url(bundle_path),
            "kind": "bundle",
        }
