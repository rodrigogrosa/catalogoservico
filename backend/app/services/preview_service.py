from __future__ import annotations

from pathlib import Path
import shutil
import zipfile

import numpy as np
from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class PreviewService:
    PREVIEWABLE_EXTENSIONS = {"stl", "obj"}
    ARCHIVE_IMAGE_HINTS = ("plate", "top", "pick", "preview", "thumbnail")
    MAIN_PREVIEW_PRIORITIES = ("thumbnail", "preview", "plate_1", "plate", "top_1", "top", "pick")
    MARKETPLACE_IMAGE_SIZE = 1600
    MARKETPLACE_LABEL_PREFIX = "marketplace_"
    MARKETPLACE_REJECT_HINTS = ("small", "middle", "no_light", "thumbnail")
    MARKETPLACE_FAMILY_PRIORITIES = ("pick", "top", "plate", "thumbnail", "preview", "generic")

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

    def generate_marketplace_ready_assets(self, previews_dir: Path, storage_root: Path) -> list[dict[str, str]]:
        if not previews_dir.exists():
            return []
        source_candidates = [path for path in sorted(previews_dir.iterdir()) if self.is_marketplace_source_candidate(path)]
        if not source_candidates:
            return []

        selected = self.select_marketplace_candidates(source_candidates)
        if not selected:
            return []

        self.clear_generated_marketplace_assets(previews_dir)
        generated: list[dict[str, str]] = []
        for index, source in enumerate(selected, start=1):
            target = previews_dir / f"{self.MARKETPLACE_LABEL_PREFIX}{index:02d}.jpg"
            self.render_marketplace_image(source, target)
            generated.append(self._artifact(target, storage_root, kind="marketplace_preview"))
        return generated

    def choose_primary_preview_url(self, previews: list[dict[str, str]] | None) -> str | None:
        if not previews:
            return None
        candidates = [preview for preview in previews if Path(str(preview.get("path", ""))).suffix.lower() in IMAGE_EXTENSIONS]
        if not candidates:
            return None

        def score(preview: dict[str, str]) -> tuple[int, str]:
            label = str(preview.get("label") or preview.get("path") or "").lower()
            if self.MARKETPLACE_LABEL_PREFIX in label:
                return -1, label
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

    def _artifact(self, file_path: Path, storage_root: Path, *, kind: str = "preview") -> dict[str, str]:
        relative = file_path.relative_to(storage_root)
        return {
            "label": file_path.name,
            "path": f"/storage/{relative.as_posix()}",
            "kind": kind,
        }

    def is_marketplace_source_candidate(self, file_path: Path) -> bool:
        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            return False
        label = file_path.name.lower()
        if label.startswith(self.MARKETPLACE_LABEL_PREFIX):
            return False
        if any(hint in label for hint in self.MARKETPLACE_REJECT_HINTS):
            return False
        return True

    def select_marketplace_candidates(self, source_candidates: list[Path]) -> list[Path]:
        scored = []
        for source in source_candidates:
            score = self.marketplace_candidate_score(source)
            if score is None:
                continue
            scored.append((score, source))
        if not scored:
            return []

        selected: list[Path] = []
        family_seen: set[str] = set()
        for _, source in sorted(scored, key=lambda item: item[0], reverse=True):
            family = self.marketplace_family(source)
            if family in family_seen and family != "generic":
                continue
            selected.append(source)
            family_seen.add(family)
            if len(selected) >= 6:
                break
        return selected

    def marketplace_candidate_score(self, source: Path) -> float | None:
        try:
            with Image.open(source) as image:
                image.load()
                width, height = image.size
                if width < 300 or height < 300:
                    return None
                bbox = self.subject_bbox(image)
                bbox_width = max(bbox[2] - bbox[0], 1)
                bbox_height = max(bbox[3] - bbox[1], 1)
                coverage = (bbox_width * bbox_height) / float(width * height)
                sharpness = self.image_sharpness(image)
                color_variation = self.image_color_variation(image)
        except Exception:
            return None

        label = source.name.lower()
        score = 0.0
        family = self.marketplace_family(source)
        family_priority = len(self.MARKETPLACE_FAMILY_PRIORITIES) - self.MARKETPLACE_FAMILY_PRIORITIES.index(family) if family in self.MARKETPLACE_FAMILY_PRIORITIES else 0
        score += family_priority * 20
        score += min(width, height) / 100
        score += min(sharpness, 1200) / 25
        if 0.08 <= coverage <= 0.82:
            score += 40
        elif coverage < 0.05:
            score -= 30
        elif coverage > 0.95:
            score -= 25
        if color_variation < 18:
            score -= 20
        if "snapmaker_compatible_final" in label:
            score += 5
        if "_01" in label:
            score -= 3
        if "thumbnail" in label:
            score -= 5
        return score

    def marketplace_family(self, source: Path) -> str:
        label = source.name.lower()
        if "pick" in label:
            return "pick"
        if "top" in label:
            return "top"
        if "plate" in label:
            return "plate"
        if "thumbnail" in label:
            return "thumbnail"
        if "preview" in label:
            return "preview"
        return "generic"

    def clear_generated_marketplace_assets(self, previews_dir: Path) -> None:
        for file_path in previews_dir.glob(f"{self.MARKETPLACE_LABEL_PREFIX}*"):
            if file_path.is_file():
                file_path.unlink(missing_ok=True)

    def render_marketplace_image(self, source: Path, target: Path) -> None:
        with Image.open(source) as image:
            image.load()
            rgba = image.convert("RGBA")
            bbox = self.subject_bbox(rgba)
            subject = rgba.crop(bbox)
            canvas = Image.new("RGBA", (self.MARKETPLACE_IMAGE_SIZE, self.MARKETPLACE_IMAGE_SIZE), (255, 255, 255, 255))

            subject_width, subject_height = subject.size
            max_dim = max(subject_width, subject_height, 1)
            scale = (self.MARKETPLACE_IMAGE_SIZE * 0.82) / max_dim
            resized = subject.resize(
                (
                    max(1, int(subject_width * scale)),
                    max(1, int(subject_height * scale)),
                ),
                Image.Resampling.LANCZOS,
            )
            offset = (
                (self.MARKETPLACE_IMAGE_SIZE - resized.size[0]) // 2,
                (self.MARKETPLACE_IMAGE_SIZE - resized.size[1]) // 2,
            )
            canvas.alpha_composite(resized, offset)
            canvas.convert("RGB").save(target, format="JPEG", quality=95, subsampling=0, optimize=True)

    def subject_bbox(self, image: Image.Image) -> tuple[int, int, int, int]:
        rgba = image.convert("RGBA")
        array = np.array(rgba)
        alpha = array[:, :, 3]
        if np.any(alpha > 16):
            ys, xs = np.where(alpha > 16)
            return self.expand_bbox(xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, rgba.size)

        rgb = array[:, :, :3].astype(np.int16)
        corners = np.vstack(
            [
                rgb[0, 0],
                rgb[0, -1],
                rgb[-1, 0],
                rgb[-1, -1],
            ]
        )
        background = np.median(corners, axis=0)
        distance = np.abs(rgb - background).sum(axis=2)
        mask = distance > 24
        if np.any(mask):
            ys, xs = np.where(mask)
            return self.expand_bbox(xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, rgba.size)
        return (0, 0, rgba.size[0], rgba.size[1])

    def expand_bbox(self, left: int, top: int, right: int, bottom: int, size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = size
        padding_x = int(max(12, (right - left) * 0.08))
        padding_y = int(max(12, (bottom - top) * 0.08))
        return (
            max(0, left - padding_x),
            max(0, top - padding_y),
            min(width, right + padding_x),
            min(height, bottom + padding_y),
        )

    def image_sharpness(self, image: Image.Image) -> float:
        grayscale = np.array(image.convert("L"), dtype=np.float32)
        if grayscale.size == 0:
            return 0.0
        gy, gx = np.gradient(grayscale)
        return float(np.var(np.abs(gx)) + np.var(np.abs(gy)))

    def image_color_variation(self, image: Image.Image) -> float:
        rgb = np.array(image.convert("RGB"), dtype=np.float32)
        if rgb.size == 0:
            return 0.0
        return float(np.mean(np.std(rgb, axis=(0, 1))))
