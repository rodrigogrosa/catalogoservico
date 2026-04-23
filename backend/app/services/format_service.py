from __future__ import annotations

from pathlib import Path
import zipfile


class FormatService:
    SUPPORTED_EXTENSIONS = {"stl", "obj", "3mf", "step", "stp", "amf", "ply", "off"}

    def detect(self, file_path: Path) -> dict[str, object]:
        extension = file_path.suffix.lower().lstrip(".")
        if extension == "slt":
            extension = "stl"
        archive_entries: list[str] = []
        source_ecosystem = "generic"
        detected_items: list[str] = []

        if zipfile.is_zipfile(file_path):
            try:
                with zipfile.ZipFile(file_path) as archive:
                    archive_entries = archive.namelist()[:200]
                if any("bambu" in entry.lower() for entry in archive_entries):
                    source_ecosystem = "bambu_lab"
                if any(entry.lower().endswith(".gcode.3mf") for entry in archive_entries):
                    source_ecosystem = "bambu_lab"
                if any(
                    entry in {
                        "Metadata/project_settings.config",
                        "Metadata/model_settings.config",
                        "Metadata/filament_sequence.json",
                    }
                    for entry in archive_entries
                ):
                    source_ecosystem = "bambu_lab"
                if any("metadata" in entry.lower() for entry in archive_entries):
                    detected_items.append("archive_metadata")
                if any(entry.lower().endswith(".png") for entry in archive_entries):
                    detected_items.append("embedded_preview")
                if any("3d/" in entry.lower() or entry.lower().endswith(".model") for entry in archive_entries):
                    detected_items.append("embedded_geometry")
                if any(entry.lower().startswith("metadata/plate_") for entry in archive_entries):
                    detected_items.append("bambu_plate_previews")
            except zipfile.BadZipFile:
                archive_entries = []

        if extension in {"3mf"} and source_ecosystem == "generic":
            source_ecosystem = "3mf_project"

        is_supported = extension in self.SUPPORTED_EXTENSIONS or bool(archive_entries)

        return {
            "extension": extension or "unknown",
            "is_supported": is_supported,
            "source_ecosystem": source_ecosystem,
            "detected_items": detected_items,
            "archive_entries": archive_entries[:50],
        }

    def detect_group(self, files: list[Path]) -> dict[str, object]:
        if not files:
            return {
                "extension": "unknown",
                "is_supported": False,
                "source_ecosystem": "generic",
                "detected_items": [],
                "archive_entries": [],
            }

        primary = next((file_path for file_path in files if file_path.suffix.lower() not in {".mtl", ".png", ".jpg", ".jpeg"}), files[0])
        payload = self.detect(primary)
        suffixes = {file_path.suffix.lower().lstrip(".") for file_path in files}
        if "obj" in suffixes:
            payload["detected_items"] = [*payload.get("detected_items", []), "obj_bundle"]
        if suffixes & {"png", "jpg", "jpeg"}:
            payload["detected_items"] = [*payload.get("detected_items", []), "texture_bundle"]
        payload["input_formats"] = sorted(suffixes)
        return payload
