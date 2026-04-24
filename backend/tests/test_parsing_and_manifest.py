from pathlib import Path
import sys
import zipfile

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.bundle_service import BundleService
from app.services.manifest_service import ManifestService
from app.services.safe_parser_service import SafeParserService
from app.services.storage_service import StorageService


def test_safe_parser_links_obj_bundle_and_reports_missing_texture(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    root = tmp_path / "obj_bundle"
    root.mkdir()
    obj_path = root / "demo.obj"
    mtl_path = root / "demo.mtl"
    obj_path.write_text("mtllib demo.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    mtl_path.write_text("newmtl mat0\nmap_Kd color.png\n", encoding="utf-8")

    parser = SafeParserService()
    result = parser.inspect_inputs([obj_path, mtl_path])

    assert not result.errors
    assert result.linked_groups[0]["group_type"] == "obj_bundle"
    assert "color.png" in result.linked_groups[0]["missing_dependencies"]
    assert any("texturas ausentes" in warning for warning in result.warnings)


def test_safe_parser_skips_huge_internal_3mf_model_during_upload_validation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("MAX_ARCHIVE_XML_PROBE_BYTES", "1024")
    get_settings.cache_clear()

    source = tmp_path / "heavy.3mf"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "3D/3dmodel.model",
            '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources/><build/></model>',
        )
        archive.writestr("Metadata/project_settings.config", "{bad-json-but-not-xml}")
        archive.writestr("3D/Objects/object_4.model", "<object>" + ("a" * 5000) + "</object>")

    parser = SafeParserService()
    result = parser.inspect_inputs([source])

    assert not result.errors
    assert any("inspeção leve aplicada em 3D/Objects/object_4.model" in warning for warning in result.warnings)
    assert any("XML/config interno inválido em Metadata/project_settings.config" in warning for warning in result.warnings)
    get_settings.cache_clear()


def test_manifest_service_writes_formal_manifest_with_hashes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    project_root = tmp_path / "storage" / "demo" / "demo_v001"
    project_root.mkdir(parents=True)
    original_dir = project_root / "original"
    original_dir.mkdir()
    source = original_dir / "part.stl"
    source.write_text("solid demo\nendsolid demo\n", encoding="utf-8")

    service = ManifestService()
    payload = service.build_manifest(
        {
            "id": "demo_v001",
            "name": "demo",
            "slug": "demo",
            "version": 1,
            "created_at": "2026-04-13T00:00:00+00:00",
            "updated_at": "2026-04-13T00:00:00+00:00",
            "original_filename": "part.stl",
            "source_ecosystem": "generic",
            "metadata": {"request_parameters": {"supports": "auto"}},
            "questions_pending": [],
        },
        [source],
        [],
    )
    written = service.write_manifest(project_root, payload)

    assert written.exists()
    data = StorageService().read_json(written)
    assert data["project_id"] == "demo_v001"
    assert data["original_files"][0]["sha256"]
    assert data["parameters"]["supports"] == "auto"


def test_bundle_service_builds_zip_with_manifest_and_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    project_root = tmp_path / "storage" / "demo" / "demo_v001"
    (project_root / "export").mkdir(parents=True)
    (project_root / "relatorios").mkdir()
    (project_root / "previews").mkdir()
    (project_root / "logs").mkdir()
    (project_root / "project_manifest.json").write_text("{}", encoding="utf-8")
    (project_root / "export" / "artifact.3mf").write_text("artifact", encoding="utf-8")
    (project_root / "relatorios" / "technical_report.md").write_text("report", encoding="utf-8")

    bundle = BundleService().build_project_bundle(project_root)

    assert bundle["path"].endswith(".zip")
    zip_path = Path(get_settings().storage_root / bundle["path"].split("/storage/", 1)[1])
    assert zip_path.exists()
