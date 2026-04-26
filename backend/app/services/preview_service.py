from __future__ import annotations

from pathlib import Path
import shutil
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import trimesh

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class PreviewService:
    PREVIEWABLE_EXTENSIONS = {"stl", "obj"}
    ARCHIVE_IMAGE_HINTS = ("plate", "top", "pick", "preview", "thumbnail")
    MAIN_PREVIEW_PRIORITIES = ("thumbnail", "preview", "plate_1", "plate", "top_1", "top", "pick")
    MARKETPLACE_IMAGE_SIZE = 1600
    MARKETPLACE_LABEL_PREFIX = "marketplace_"
    MARKETPLACE_REJECT_HINTS = ("small", "thumbnail_3mf")
    MARKETPLACE_FAMILY_PRIORITIES = ("plate", "pick", "top", "thumbnail", "preview", "generic")

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

    def generate_marketplace_ready_assets(
        self,
        previews_dir: Path,
        storage_root: Path,
        source_files: list[Path] | None = None,
        *,
        force: bool = False,
    ) -> list[dict[str, str]]:
        if not previews_dir.exists():
            return []
        existing_marketplace_assets = [
            self._artifact(file_path, storage_root, kind="marketplace_preview")
            for file_path in sorted(previews_dir.glob(f"{self.MARKETPLACE_LABEL_PREFIX}*.jpg"))
            if file_path.is_file()
        ]
        if existing_marketplace_assets and not force:
            return existing_marketplace_assets
        source_candidates = [path for path in sorted(previews_dir.iterdir()) if self.is_marketplace_source_candidate(path)]
        if not source_candidates:
            return existing_marketplace_assets

        analyses = self.analyze_marketplace_candidates(source_candidates)
        clean_render = self.select_best_analysis(
            analyses,
            preferred_kind="clean_render",
            preferred_family="plate",
        ) or self.select_best_analysis(analyses, preferred_kind="clean_render")
        if clean_render is None:
            return []
        lifestyle = self.select_best_analysis(analyses, preferred_kind="lifestyle")
        top_render = self.select_best_analysis(
            [analysis for analysis in analyses if analysis["path"] != clean_render["path"]],
            preferred_kind="clean_render",
            preferred_family="top",
        )
        dimensions_mm = self.infer_dimensions_mm(source_files or [])

        self.clear_generated_marketplace_assets(previews_dir)
        generated: list[dict[str, str]] = []
        render_plan: list[tuple[str, dict[str, object] | None]] = [
            ("hero", clean_render),
            ("dimensions", clean_render),
            ("lifestyle", lifestyle or top_render or clean_render),
        ]
        for index, (variant, analysis) in enumerate(render_plan, start=1):
            if analysis is None:
                continue
            target = previews_dir / f"{self.MARKETPLACE_LABEL_PREFIX}{index:02d}.jpg"
            if variant == "hero":
                self.render_marketplace_hero(Path(str(analysis["path"])), target)
            elif variant == "dimensions":
                self.render_marketplace_dimensions(Path(str(analysis["path"])), target, dimensions_mm)
            else:
                self.render_marketplace_lifestyle(Path(str(analysis["path"])), target, analysis)
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

    def analyze_marketplace_candidates(self, source_candidates: list[Path]) -> list[dict[str, object]]:
        analyses: list[dict[str, object]] = []
        for source in source_candidates:
            analysis = self.marketplace_candidate_analysis(source)
            if analysis is not None:
                analyses.append(analysis)
        return analyses

    def select_best_analysis(
        self,
        analyses: list[dict[str, object]],
        *,
        preferred_kind: str,
        preferred_family: str | None = None,
    ) -> dict[str, object] | None:
        filtered = [item for item in analyses if item["kind"] == preferred_kind]
        if preferred_family:
            preferred = [item for item in filtered if item["family"] == preferred_family]
            if preferred:
                return sorted(preferred, key=lambda item: float(item["score"]), reverse=True)[0]
        if filtered:
            return sorted(filtered, key=lambda item: float(item["score"]), reverse=True)[0]
        return None

    def marketplace_candidate_analysis(self, source: Path) -> dict[str, object] | None:
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
                color_buckets = self.image_color_bucket_count(image, bbox)
                background_brightness = self.image_background_brightness(image)
        except Exception:
            return None

        label = source.name.lower()
        family = self.marketplace_family(source)
        family_priority = len(self.MARKETPLACE_FAMILY_PRIORITIES) - self.MARKETPLACE_FAMILY_PRIORITIES.index(family) if family in self.MARKETPLACE_FAMILY_PRIORITIES else 0
        if background_brightness < 8 and color_buckets < 30:
            return None
        if color_buckets < 18 and color_variation < 18:
            return None

        kind = "lifestyle" if background_brightness > 25 and color_buckets > 250 else "clean_render"
        score = 0.0
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
        if kind == "lifestyle":
            score += 35
        return {
            "path": source,
            "family": family,
            "kind": kind,
            "score": score,
            "width": width,
            "height": height,
            "coverage": coverage,
            "sharpness": sharpness,
            "color_variation": color_variation,
            "color_buckets": color_buckets,
            "background_brightness": background_brightness,
        }

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

    def render_marketplace_hero(self, source: Path, target: Path) -> None:
        with Image.open(source) as image:
            image.load()
            rgba = image.convert("RGBA")
            bbox = self.subject_bbox(rgba)
            subject = rgba.crop(bbox)
            canvas = Image.new("RGBA", (self.MARKETPLACE_IMAGE_SIZE, self.MARKETPLACE_IMAGE_SIZE), (250, 250, 248, 255))

            subject_width, subject_height = subject.size
            max_dim = max(subject_width, subject_height, 1)
            scale = (self.MARKETPLACE_IMAGE_SIZE * 0.66) / max_dim
            resized = subject.resize(
                (
                    max(1, int(subject_width * scale)),
                    max(1, int(subject_height * scale)),
                ),
                Image.Resampling.LANCZOS,
            )
            shadow = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_box = (
                int(self.MARKETPLACE_IMAGE_SIZE * 0.25),
                int(self.MARKETPLACE_IMAGE_SIZE * 0.68),
                int(self.MARKETPLACE_IMAGE_SIZE * 0.75),
                int(self.MARKETPLACE_IMAGE_SIZE * 0.82),
            )
            shadow_draw.ellipse(shadow_box, fill=(0, 0, 0, 70))
            shadow = shadow.filter(ImageFilter.GaussianBlur(36))
            canvas.alpha_composite(shadow)
            offset = (
                (self.MARKETPLACE_IMAGE_SIZE - resized.size[0]) // 2,
                int(self.MARKETPLACE_IMAGE_SIZE * 0.23),
            )
            canvas.alpha_composite(resized, offset)
            final = canvas.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.6, percent=130, threshold=2))
            final.save(target, format="JPEG", quality=96, subsampling=0, optimize=True)

    def render_marketplace_dimensions(self, source: Path, target: Path, dimensions_mm: tuple[float, float, float] | None) -> None:
        with Image.open(source) as image:
            image.load()
            rgba = image.convert("RGBA")
            bbox = self.subject_bbox(rgba)
            subject = rgba.crop(bbox)

        canvas = Image.new("RGBA", (self.MARKETPLACE_IMAGE_SIZE, self.MARKETPLACE_IMAGE_SIZE), (250, 250, 248, 255))
        draw = ImageDraw.Draw(canvas)
        title_font = ImageFont.load_default(size=44)
        body_font = ImageFont.load_default(size=28)
        draw.text((120, 110), "Escala aproximada do produto", fill=(17, 24, 39, 255), font=title_font)
        if dimensions_mm:
            x, y, z = dimensions_mm
            lines = [
                f"Largura: {x/10:.1f} cm",
                f"Altura: {y/10:.1f} cm",
                f"Profundidade: {z/10:.1f} cm",
            ]
        else:
            lines = ["Medidas aproximadas", "consulte o catálogo", "para escala final."]
        for index, line in enumerate(lines):
            draw.rounded_rectangle((120, 220 + index * 120, 620, 300 + index * 120), radius=28, fill=(255, 255, 255, 255), outline=(230, 232, 235, 255), width=2)
            draw.text((150, 248 + index * 120), line, fill=(48, 63, 84, 255), font=body_font)

        subject_width, subject_height = subject.size
        max_dim = max(subject_width, subject_height, 1)
        scale = 780 / max_dim
        resized = subject.resize((max(1, int(subject_width * scale)), max(1, int(subject_height * scale))), Image.Resampling.LANCZOS)
        shadow = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.ellipse((860, 1140, 1460, 1280), fill=(0, 0, 0, 55))
        shadow = shadow.filter(ImageFilter.GaussianBlur(30))
        canvas.alpha_composite(shadow)
        model_pos = (900, 330)
        canvas.alpha_composite(resized, model_pos)

        if dimensions_mm:
            x, y, z = dimensions_mm
            arrow_color = (180, 96, 28, 255)
            left = model_pos[0]
            top = model_pos[1]
            right = model_pos[0] + resized.size[0]
            bottom = model_pos[1] + resized.size[1]
            mid_x = (left + right) // 2
            mid_y = (top + bottom) // 2
            draw.line((left - 40, top, left - 40, bottom), fill=arrow_color, width=4)
            draw.polygon([(left - 40, top), (left - 52, top + 18), (left - 28, top + 18)], fill=arrow_color)
            draw.polygon([(left - 40, bottom), (left - 52, bottom - 18), (left - 28, bottom - 18)], fill=arrow_color)
            draw.text((left - 92, mid_y - 12), f"{y/10:.1f} cm", fill=arrow_color, font=body_font)

            draw.line((left, bottom + 48, right, bottom + 48), fill=arrow_color, width=4)
            draw.polygon([(left, bottom + 48), (left + 18, bottom + 36), (left + 18, bottom + 60)], fill=arrow_color)
            draw.polygon([(right, bottom + 48), (right - 18, bottom + 36), (right - 18, bottom + 60)], fill=arrow_color)
            draw.text((mid_x - 48, bottom + 62), f"{x/10:.1f} cm", fill=arrow_color, font=body_font)

            draw.text((right + 30, top + 40), f"prof.\n{z/10:.1f} cm", fill=arrow_color, font=body_font)

        canvas.convert("RGB").save(target, format="JPEG", quality=96, subsampling=0, optimize=True)

    def render_marketplace_lifestyle(self, source: Path, target: Path, analysis: dict[str, object]) -> None:
        if analysis["kind"] == "lifestyle":
            with Image.open(source) as image:
                image.load()
                rgb = image.convert("RGB")
                canvas = Image.new("RGB", (self.MARKETPLACE_IMAGE_SIZE, self.MARKETPLACE_IMAGE_SIZE), (250, 250, 248))
                frame = Image.new("RGB", (1320, 990), (255, 255, 255))
                photo = rgb.resize((1260, 946), Image.Resampling.LANCZOS)
                shadow = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
                shadow_draw = ImageDraw.Draw(shadow)
                shadow_draw.rounded_rectangle((150, 200, 1450, 1190), radius=40, fill=(0, 0, 0, 55))
                shadow = shadow.filter(ImageFilter.GaussianBlur(36))
                canvas_rgba = canvas.convert("RGBA")
                canvas_rgba.alpha_composite(shadow)
                canvas_rgba.alpha_composite(frame.convert("RGBA"), (140, 190))
                canvas_rgba.alpha_composite(photo.convert("RGBA"), (170, 212))
                canvas_rgba.convert("RGB").save(target, format="JPEG", quality=95, subsampling=0, optimize=True)
                return
        self.render_marketplace_hero(source, target)

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

    def image_color_bucket_count(self, image: Image.Image, bbox: tuple[int, int, int, int]) -> int:
        cropped = np.array(image.crop(bbox).convert("RGB"))
        if cropped.size == 0:
            return 0
        quantized = (cropped.reshape(-1, 3) // 16).astype(int)
        return len({tuple(pixel) for pixel in quantized})

    def image_background_brightness(self, image: Image.Image) -> float:
        rgb = np.array(image.convert("RGB"))
        corners = np.vstack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
        return float(np.mean(corners))

    def infer_dimensions_mm(self, source_files: list[Path]) -> tuple[float, float, float] | None:
        for file_path in source_files:
            if not file_path.exists() or file_path.suffix.lower() not in {".3mf", ".stl", ".obj", ".ply"}:
                continue
            try:
                scene = trimesh.load(file_path, force="scene")
                extents = getattr(scene, "extents", None)
                if extents is None and hasattr(scene, "geometry") and scene.geometry:
                    extents = next(iter(scene.geometry.values())).extents
                if extents is None:
                    continue
                values = tuple(round(float(value), 1) for value in extents[:3])
                if len(values) == 3 and all(value > 0 for value in values):
                    return values
            except Exception:
                continue
        return None
