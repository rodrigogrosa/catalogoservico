from __future__ import annotations

from pathlib import Path
import shutil
import zipfile

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class PreviewService:
    PREVIEWABLE_EXTENSIONS = {"stl", "obj"}
    ARCHIVE_IMAGE_HINTS = ("plate", "top", "pick", "preview", "thumbnail")
    MAIN_PREVIEW_PRIORITIES = ("thumbnail", "preview", "plate_1", "plate", "top_1", "top", "pick")

    def build_preview_url(self, file_path: Path, storage_root: Path) -> str | None:
        extension = file_path.suffix.lower().lstrip(".")
        if extension == "slt":
            extension = "stl"
        if extension not in self.PREVIEWABLE_EXTENSIONS:
            return None
        relative = file_path.relative_to(storage_root)
        return f"/storage/{relative.as_posix()}"

    def extract_preview_assets(
        self,
        file_path: Path,
        previews_dir: Path,
        storage_root: Path,
        label_prefix: str,
    ) -> list[dict[str, str]]:
        assets: list[dict[str, str]] = []
        extension = file_path.suffix.lower()

        if extension in IMAGE_EXTENSIONS:
            target = self._copy_unique(file_path, previews_dir, f"{label_prefix}_{file_path.name}")
            return [self._artifact(target, storage_root)]

        if extension in {".obj", ".mtl"}:
            return []

        if extension != ".3mf" or not zipfile.is_zipfile(file_path):
            return []

        try:
            with zipfile.ZipFile(file_path) as archive:
                candidates = [
                    name
                    for name in archive.namelist()
                    if Path(name).suffix.lower() in IMAGE_EXTENSIONS
                    and any(hint in Path(name).name.lower() for hint in self.ARCHIVE_IMAGE_HINTS)
                ]
                for name in candidates:
                    target = previews_dir / f"{label_prefix}_{Path(name).name}"
                    target = self._unique_path(target)
                    target.write_bytes(archive.read(name))
                    assets.append(self._artifact(target, storage_root))
        except Exception:
            return []

        return assets

    def collect_existing_previews(self, previews_dir: Path, storage_root: Path) -> list[dict[str, str]]:
        if not previews_dir.exists():
            return []
        assets: list[dict[str, str]] = []
        for file_path in sorted(previews_dir.iterdir()):
            if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            assets.append(self._artifact(file_path, storage_root))
        return assets

    def choose_primary_preview_url(self, previews: list[dict[str, str]] | None) -> str | None:
        if not previews:
            return None
        candidates = [preview for preview in previews if Path(str(preview.get("path", ""))).suffix.lower() in IMAGE_EXTENSIONS]
        if not candidates:
            return None

        def score(preview: dict[str, str]) -> tuple[int, str]:
            label = str(preview.get("label") or preview.get("path") or "").lower()
            priority = next((index for index, marker in enumerate(self.MAIN_PREVIEW_PRIORITIES) if marker in label), len(self.MAIN_PREVIEW_PRIORITIES))
            return priority, label

        selected = sorted(candidates, key=score)[0]
        return selected.get("path")

    def _copy_unique(self, source: Path, previews_dir: Path, target_name: str) -> Path:
        destination = self._unique_path(previews_dir / target_name)
        shutil.copy2(source, destination)
        return destination

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        index = 1
        while True:
            candidate = path.with_name(f"{path.stem}_{index:02d}{path.suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    def _artifact(self, file_path: Path, storage_root: Path) -> dict[str, str]:
        relative = file_path.relative_to(storage_root)
        return {
            "label": file_path.name,
            "path": f"/storage/{relative.as_posix()}",
            "kind": "preview",
        }
