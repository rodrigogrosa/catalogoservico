from pathlib import Path
import sys

from PIL import Image, ImageDraw


from app.services.preview_service import PreviewService
from app.services.project_service import ProjectService
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


def test_store_service_includes_all_preview_images() -> None:
    """All previews are included so the user sees all photos in the listing (not just marketplace_preview ones)."""
    project = {
        "preview_url": "/storage/project/previews/raw.png",
        "previews": [
            {"label": "raw.png", "path": "/storage/project/previews/raw.png", "kind": "preview"},
            {"label": "marketplace_01.jpg", "path": "/storage/project/previews/marketplace_01.jpg", "kind": "marketplace_preview"},
        ],
    }
    store = {"settings": {}}

    public = StoreService().resolve_product_images(project, None, store)

    base = "https://api.euachei3d.com.br"
    assert f"{base}/storage/project/previews/raw.png" in public
    assert f"{base}/storage/project/previews/marketplace_01.jpg" in public
    assert len(public) == 2


def test_infer_dimensions_does_not_parse_3mf_with_trimesh(monkeypatch, tmp_path: Path) -> None:
    service = PreviewService()
    project_3mf = tmp_path / "sample.3mf"
    project_3mf.write_bytes(b"placeholder")

    called = {"value": False}

    def fake_load(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("trimesh.load nao deveria ser chamado para 3mf no caminho de preview")

    monkeypatch.setattr("app.services.preview_service.trimesh.load", fake_load)

    dimensions = service.infer_dimensions_mm([project_3mf])

    assert dimensions is None
    assert called["value"] is False


def test_infer_dimensions_skips_large_mesh_files(monkeypatch, tmp_path: Path) -> None:
    service = PreviewService()
    big_stl = tmp_path / "huge.stl"
    big_stl.write_bytes(b"x" * (service.MAX_DIMENSION_INFER_FILE_BYTES + 1))

    called = {"value": False}

    def fake_load(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("trimesh.load nao deveria ser chamado para arquivo grande no caminho de preview")

    monkeypatch.setattr("app.services.preview_service.trimesh.load", fake_load)

    dimensions = service.infer_dimensions_mm([big_stl])

    assert dimensions is None
    assert called["value"] is False


def test_collect_previews_does_not_generate_marketplace_assets_synchronously(monkeypatch, tmp_path: Path) -> None:
    previews_dir = tmp_path / "previews"
    previews_dir.mkdir()
    source = tmp_path / "sample.3mf"
    source.write_bytes(b"not-a-valid-3mf")

    service = ProjectService()
    called = {"value": False}

    def fail_if_called(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("generate_marketplace_ready_assets nao deve rodar no caminho síncrono de upload")

    monkeypatch.setattr(service.preview_service, "generate_marketplace_ready_assets", fail_if_called)
    service.collect_previews([source], previews_dir)

    assert called["value"] is False
