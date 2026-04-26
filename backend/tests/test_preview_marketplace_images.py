from pathlib import Path
import sys

from PIL import Image, ImageDraw

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.preview_service import PreviewService
from app.services.store_service import StoreService


def build_transparent_subject(path: Path, *, size: tuple[int, int], shape_box: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(shape_box, fill=(30, 200, 70, 255))
    image.save(path)


def test_generate_marketplace_ready_assets_creates_square_commercial_images(tmp_path: Path) -> None:
    previews_dir = tmp_path / "previews"
    previews_dir.mkdir()
    build_transparent_subject(previews_dir / "bird_pick_1.png", size=(1200, 900), shape_box=(200, 180, 980, 780))
    build_transparent_subject(previews_dir / "bird_top_1.png", size=(1100, 1100), shape_box=(160, 180, 940, 920))
    build_transparent_subject(previews_dir / "bird_thumbnail_small.png", size=(280, 280), shape_box=(20, 20, 250, 250))

    assets = PreviewService().generate_marketplace_ready_assets(previews_dir, tmp_path)

    assert assets
    assert all(item["kind"] == "marketplace_preview" for item in assets)
    generated_paths = [tmp_path / item["path"].removeprefix("/storage/") for item in assets]
    assert all(path.exists() for path in generated_paths)

    with Image.open(generated_paths[0]) as generated:
        assert generated.size == (1600, 1600)
        assert generated.mode == "RGB"


def test_store_service_prefers_marketplace_preview_images() -> None:
    project = {
        "preview_url": "/storage/project/previews/raw.png",
        "previews": [
            {"label": "raw.png", "path": "/storage/project/previews/raw.png", "kind": "preview"},
            {"label": "marketplace_01.jpg", "path": "/storage/project/previews/marketplace_01.jpg", "kind": "marketplace_preview"},
        ],
    }
    store = {"settings": {}}

    public = StoreService().resolve_product_images(project, None, store)

    assert public == ["https://api.euachei3d.com.br/storage/project/previews/marketplace_01.jpg"]
