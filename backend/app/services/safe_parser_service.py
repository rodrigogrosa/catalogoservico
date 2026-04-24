from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Any
import zipfile
from xml.etree import ElementTree as ET

import filetype

from app.core.config import get_settings


@dataclass
class ParsingResult:
    errors: list[str]
    warnings: list[str]
    detected_files: list[dict[str, Any]]
    linked_groups: list[dict[str, Any]]
    metadata: dict[str, Any]


class SafeParserService:
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    def __init__(self) -> None:
        self.settings = get_settings()

    def inspect_inputs(self, files: list[Path]) -> ParsingResult:
        errors: list[str] = []
        warnings: list[str] = []
        detected_files: list[dict[str, Any]] = []

        if not files:
            return ParsingResult(
                errors=["Nenhum arquivo foi enviado."],
                warnings=[],
                detected_files=[],
                linked_groups=[],
                metadata={},
            )

        if len(files) > self.settings.max_project_files:
            errors.append(
                f"O projeto excede o limite configurado de {self.settings.max_project_files} arquivos relacionados."
            )

        for file_path in files:
            detected_files.append(self._inspect_file(file_path, errors, warnings))

        linked_groups = self._link_related_files(files, warnings, errors)
        metadata = self._build_metadata(files, linked_groups)
        return ParsingResult(errors=errors, warnings=warnings, detected_files=detected_files, linked_groups=linked_groups, metadata=metadata)

    def _inspect_file(self, file_path: Path, errors: list[str], warnings: list[str]) -> dict[str, Any]:
        suffix = file_path.suffix.lower()
        size_bytes = file_path.stat().st_size if file_path.exists() else 0
        entry: dict[str, Any] = {
            "name": file_path.name,
            "path": str(file_path),
            "suffix": suffix,
            "size_bytes": size_bytes,
            "kind_guess": None,
            "status": "ok",
            "details": [],
        }

        if size_bytes == 0:
            errors.append(f"Arquivo vazio detectado: {file_path.name}.")
            entry["status"] = "failed"
            return entry

        kind = filetype.guess(file_path)
        entry["kind_guess"] = kind.mime if kind else "unknown"

        try:
            if suffix == ".3mf":
                self._validate_zip_like(file_path, errors, warnings, entry, expect_model=True)
            elif suffix == ".zip":
                self._validate_zip_like(file_path, errors, warnings, entry, expect_model=False)
            elif suffix == ".stl":
                self._validate_stl(file_path, errors, warnings, entry)
            elif suffix == ".obj":
                self._validate_obj(file_path, warnings, entry)
            elif suffix in {".png", ".jpg", ".jpeg"}:
                entry["details"].append("Texture/image resource accepted.")
            elif suffix in {".mtl", ".step", ".stp", ".amf", ".ply", ".off"}:
                entry["details"].append("Resource accepted for grouped processing.")
            else:
                warnings.append(f"Extensão {suffix or 'desconhecida'} será tratada com validação conservadora.")
        except Exception as exc:
            errors.append(f"Falha na inspeção de {file_path.name}: {exc}")
            entry["status"] = "failed"

        return entry

    def _validate_zip_like(
        self,
        file_path: Path,
        errors: list[str],
        warnings: list[str],
        entry: dict[str, Any],
        expect_model: bool,
    ) -> None:
        if not zipfile.is_zipfile(file_path):
            errors.append(f"{file_path.name} não é um ZIP/3MF válido.")
            entry["status"] = "failed"
            return

        with zipfile.ZipFile(file_path) as archive:
            infos = archive.infolist()
            if len(infos) > self.settings.max_zip_entries:
                errors.append(f"{file_path.name} excede o limite de {self.settings.max_zip_entries} entradas internas.")
                entry["status"] = "failed"
                return
            names = [item.filename for item in infos]
            max_depth = max((name.count("/") for name in names), default=0)
            if max_depth > self.settings.max_zip_depth:
                errors.append(f"{file_path.name} excede a profundidade máxima de ZIP configurada.")
                entry["status"] = "failed"
                return
            if expect_model and not any(name.lower().endswith(".model") for name in names):
                errors.append(f"{file_path.name} não contém nenhum 3dmodel.model/.model interno.")
                entry["status"] = "failed"
                return

            candidate_infos = [
                info
                for info in infos
                if info.filename.lower().endswith((".model", ".xml", ".rels", ".config"))
            ]
            candidate_infos.sort(key=self._archive_probe_priority)
            for info in candidate_infos[:20]:
                name = info.filename
                if info.file_size > self.settings.max_archive_xml_probe_bytes:
                    warnings.append(
                        f"{file_path.name}: inspeção leve aplicada em {name} ({info.file_size} bytes internos); "
                        "arquivo interno muito grande para validação XML completa no upload."
                    )
                    continue
                try:
                    ET.fromstring(archive.read(name))
                except ET.ParseError:
                    if name.lower().endswith(".config"):
                        warnings.append(f"{file_path.name}: XML/config interno inválido em {name}.")
                    else:
                        errors.append(f"{file_path.name}: XML interno inválido em {name}.")

    def _archive_probe_priority(self, info: zipfile.ZipInfo) -> tuple[int, int, str]:
        name = info.filename.lower()
        if name == "3d/3dmodel.model":
            priority = 0
        elif name.endswith(".config"):
            priority = 1
        elif name.endswith(".xml"):
            priority = 2
        elif name.endswith(".rels"):
            priority = 3
        elif "/objects/" in name and name.endswith(".model"):
            priority = 5
        else:
            priority = 4
        return priority, info.file_size, name

    def _validate_stl(self, file_path: Path, errors: list[str], warnings: list[str], entry: dict[str, Any]) -> None:
        with file_path.open("rb") as handle:
            header = handle.read(84)
            if len(header) < 84:
                errors.append(f"STL truncado: {file_path.name}.")
                entry["status"] = "failed"
                return
            triangle_count = struct.unpack("<I", header[80:84])[0]
            expected_size = 84 + triangle_count * 50
            actual_size = file_path.stat().st_size
            if actual_size != expected_size:
                warnings.append(
                    f"STL {file_path.name} tem tamanho inconsistente com o cabeçalho binário; possível truncamento ou STL ASCII com extensão binária."
                )
                if actual_size < expected_size:
                    errors.append(f"STL truncado detectado: {file_path.name}.")
                    entry["status"] = "failed"

    def _validate_obj(self, file_path: Path, warnings: list[str], entry: dict[str, Any]) -> None:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if "v " not in content and "f " not in content:
            entry["status"] = "failed"
            raise ValueError("OBJ sem vértices/faces válidos.")
        mtllibs = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("mtllib "):
                mtllibs.append(stripped.split(maxsplit=1)[1].strip())
        entry["details"].append(f"OBJ references {len(mtllibs)} material libraries.")
        if not mtllibs:
            warnings.append(f"{file_path.name} não referencia nenhum MTL; cores/texturas podem não ser preservadas.")

    def _link_related_files(
        self,
        files: list[Path],
        warnings: list[str],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        by_name = {file_path.name: file_path for file_path in files}
        groups: list[dict[str, Any]] = []
        obj_files = [file_path for file_path in files if file_path.suffix.lower() == ".obj"]
        for obj_file in obj_files:
            content = obj_file.read_text(encoding="utf-8", errors="ignore")
            mtllibs = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("mtllib "):
                    mtllibs.append(stripped.split(maxsplit=1)[1].strip())

            linked_textures: set[str] = set()
            missing_mtllibs: list[str] = []
            for mtl_name in mtllibs:
                mtl_file = by_name.get(mtl_name)
                if mtl_file is None:
                    missing_mtllibs.append(mtl_name)
                    continue
                mtl_content = mtl_file.read_text(encoding="utf-8", errors="ignore")
                for line in mtl_content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("map_Kd ", "map_d ", "bump ", "map_Bump ")):
                        texture_name = stripped.split(maxsplit=1)[1].strip()
                        linked_textures.add(texture_name)

            missing_textures = sorted(name for name in linked_textures if name not in by_name)
            if missing_mtllibs:
                warnings.append(f"{obj_file.name} referencia MTL ausente: {', '.join(missing_mtllibs)}.")
            if missing_textures:
                warnings.append(f"{obj_file.name} referencia texturas ausentes: {', '.join(missing_textures)}.")

            groups.append(
                {
                    "group_type": "obj_bundle",
                    "root_file": obj_file.name,
                    "files": [obj_file.name, *mtllibs, *sorted(linked_textures)],
                    "missing_dependencies": [*missing_mtllibs, *missing_textures],
                    "color_intent_detected": bool(mtllibs or linked_textures),
                }
            )
        return groups

    def _build_metadata(self, files: list[Path], linked_groups: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "input_file_count": len(files),
            "group_types": sorted({group["group_type"] for group in linked_groups}),
            "has_obj_bundle": any(group["group_type"] == "obj_bundle" for group in linked_groups),
            "texture_intent_detected": any(group.get("color_intent_detected") for group in linked_groups),
        }
