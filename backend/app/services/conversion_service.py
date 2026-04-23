from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

from app.core.config import get_settings
from app.services.storage_service import StorageService

ET.register_namespace("", "http://schemas.microsoft.com/3dmanufacturing/core/2015/02")
ET.register_namespace("p", "http://schemas.microsoft.com/3dmanufacturing/production/2015/06")
ET.register_namespace("BambuStudio", "http://schemas.bambulab.com/package/2021")


class ConversionService:
    CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
    SNAPMAKER_PROFILE_NAME = "Snapmaker U1 0.4 nozzle"
    SNAPMAKER_START_GCODE = """; SnapMaker3d Studio sanitized start gcode
G90
M82
G21
G28
M140 S[bed_temperature_initial_layer_single]
M190 S[bed_temperature_initial_layer_single]
M104 S[nozzle_temperature_initial_layer]
M109 S[nozzle_temperature_initial_layer]
G92 E0
"""
    SNAPMAKER_END_GCODE = """; SnapMaker3d Studio sanitized end gcode
G92 E0
G1 E-1.0 F1800
M104 S0
M140 S0
M107
G91
G1 Z10 F600
G90
G1 X0 Y220 F6000
M84
"""
    SNAPMAKER_LAYER_CHANGE_GCODE = """; layer {layer_num+1}
"""
    SNAPMAKER_FILAMENT_START_GCODE = "; SnapMaker3d Studio sanitized filament start gcode\n"
    SNAPMAKER_FILAMENT_END_GCODE = "; SnapMaker3d Studio sanitized filament end gcode\n"

    def __init__(self) -> None:
        self.storage = StorageService()
        self.settings = get_settings()

    def inspect_bambu_project(self, source_file: Path) -> dict[str, Any]:
        if not zipfile.is_zipfile(source_file):
            return {
                "status": "partial",
                "detected_items": [],
                "findings": ["Arquivo nao e um pacote compactado reconhecido do ecossistema Bambu."],
            }

        with zipfile.ZipFile(source_file) as archive:
            entries = archive.namelist()
        detected_items = []
        if any("plate" in entry.lower() for entry in entries):
            detected_items.append("plates")
        if any("filament" in entry.lower() for entry in entries):
            detected_items.append("filament_profiles")
        if any("paint" in entry.lower() or "color" in entry.lower() for entry in entries):
            detected_items.append("multicolor_data")
        if any("modifier" in entry.lower() for entry in entries):
            detected_items.append("modifier_meshes")
        if any("negative" in entry.lower() for entry in entries):
            detected_items.append("negative_volumes")
        if any("support" in entry.lower() and "block" in entry.lower() for entry in entries):
            detected_items.append("support_blockers")
        if any("support" in entry.lower() and "enforce" in entry.lower() for entry in entries):
            detected_items.append("support_enforcers")
        if any("assembly" in entry.lower() for entry in entries):
            detected_items.append("assemblies")
        if any(entry.lower().endswith(".model") for entry in entries):
            detected_items.append("geometry_models")
        return {
            "status": "ok",
            "detected_items": detected_items,
            "findings": [f"{len(entries)} entradas inspecionadas no pacote Bambu/3MF."],
            "archive_entries": entries[:50],
        }

    def convert_to_snapmaker(
        self,
        source_file: Path,
        export_dir: Path,
        support_plan: dict[str, Any] | None = None,
        adhesion_plan: dict[str, Any] | None = None,
        scale_mode: str | None = None,
    ) -> dict[str, Any]:
        destination = self.storage.next_generated_file(
            export_dir,
            f"{source_file.stem}_snapmaker_compatible",
            source_file.suffix,
        )
        preserved = ["geometria bruta", "estrutura basica de arquivos"]
        adapted = ["metadados de projeto sinalizados para reconfiguracao manual no fluxo Snapmaker"]
        lost = ["equivalencias exatas de slicing/profiles proprietarios nao garantidas nesta versao base"]

        if zipfile.is_zipfile(source_file):
            sanitized = self._sanitize_project_archive(
                source_file,
                destination,
                support_plan=support_plan,
                adhesion_plan=adhesion_plan,
                scale_mode=scale_mode,
            )
            adapted.extend(sanitized["adapted"])
            lost.extend(sanitized["lost"])
            extra_output_files = sanitized.get("extra_output_files", [])
            parameter_equivalence = sanitized.get("parameter_equivalence", [])
        else:
            shutil.copy2(source_file, destination)
            extra_output_files = []
            parameter_equivalence = []

        return {
            "status": "partial",
            "output_file": str(destination),
            "extra_output_files": extra_output_files,
            "preserved": preserved,
            "adapted": adapted,
            "lost": lost,
            "support_plan": support_plan or {"enabled": False, "reason": "not_provided"},
            "adhesion_plan": adhesion_plan or {"mode": "skirt", "reason": "not_provided"},
            "parameter_equivalence": parameter_equivalence,
        }

    def _sanitize_project_archive(
        self,
        source_file: Path,
        destination: Path,
        support_plan: dict[str, Any] | None = None,
        adhesion_plan: dict[str, Any] | None = None,
        scale_mode: str | None = None,
    ) -> dict[str, list[str] | list[dict[str, Any]]]:
        adapted: list[str] = []
        lost: list[str] = []
        parameter_equivalence: list[dict[str, Any]] = []
        with zipfile.ZipFile(source_file, "r") as source_zip:
            entries = {info.filename: source_zip.read(info.filename) for info in source_zip.infolist()}

        if "Metadata/project_settings.config" in entries:
            try:
                settings = json.loads(entries["Metadata/project_settings.config"].decode("utf-8"))
                settings, applied, equivalence = self._sanitize_project_settings(
                    settings,
                    support_plan=support_plan,
                    adhesion_plan=adhesion_plan,
                )
                adapted.extend(applied)
                parameter_equivalence.extend(equivalence)
                entries["Metadata/project_settings.config"] = json.dumps(
                    settings,
                    indent=4,
                    ensure_ascii=False,
                ).encode("utf-8")
            except Exception:
                lost.append(
                    "sanitizacao automatica de project_settings.config falhou; configuracao original foi preservada"
                )

        if self._has_plate_metadata(entries) and source_file.stat().st_size >= 20 * 1024 * 1024:
            preserved_entries, preserved_adapted, preserved_lost = self._build_snapmaker_plate_preserving_package(
                entries,
                preserve_all_entries=True,
            )
            adapted.extend(preserved_adapted)
            lost.extend(preserved_lost)
            self._write_archive(destination, preserved_entries)
            return {
                "adapted": adapted,
                "lost": lost,
                "extra_output_files": [],
                "parameter_equivalence": parameter_equivalence,
            }

        entries, inline_adapted, inline_lost = self._inline_external_geometry(entries)
        adapted.extend(inline_adapted)
        lost.extend(inline_lost)

        if self._has_plate_metadata(entries):
            entries, cleanup_adapted, cleanup_lost = self._finalize_root_only_package(entries)
            adapted.extend(cleanup_adapted)
            lost.extend(cleanup_lost)

            preserved_entries, preserved_adapted, preserved_lost = self._build_snapmaker_plate_preserving_package(entries)
            adapted.extend(preserved_adapted)
            lost.extend(preserved_lost)
            self._write_archive(destination, preserved_entries)
            return {
                "adapted": adapted,
                "lost": lost,
                "extra_output_files": [],
                "parameter_equivalence": parameter_equivalence,
            }

        entries, flattened_adapted, flattened_lost = self._flatten_composite_build_items(entries)
        adapted.extend(flattened_adapted)
        lost.extend(flattened_lost)

        entries, cleanup_adapted, cleanup_lost = self._finalize_root_only_package(entries)
        adapted.extend(cleanup_adapted)
        lost.extend(cleanup_lost)

        normalized_entries, extra_root_models, layout_adapted, layout_lost = self._normalize_and_split_layout(
            entries,
            scale_mode=scale_mode,
        )
        adapted.extend(layout_adapted)
        lost.extend(layout_lost)

        normalized_entries, baked_adapted, baked_lost = self._bake_build_items_to_direct_meshes(normalized_entries)
        adapted.extend(baked_adapted)
        lost.extend(baked_lost)

        normalized_entries, fit_adapted, fit_lost = self._fit_root_meshes_within_plate(normalized_entries)
        adapted.extend(fit_adapted)
        lost.extend(fit_lost)

        minimal_entries, minimal_adapted = self._build_snapmaker_safe_package(normalized_entries)
        adapted.extend(minimal_adapted)

        self._write_archive(destination, minimal_entries)
        extra_output_files: list[str] = []

        return {
            "adapted": adapted,
            "lost": lost,
            "extra_output_files": extra_output_files,
            "parameter_equivalence": parameter_equivalence,
        }

    def _has_plate_metadata(self, entries: dict[str, bytes]) -> bool:
        model_settings = entries.get("Metadata/model_settings.config")
        if not model_settings:
            return False
        try:
            root = ET.fromstring(model_settings)
        except ET.ParseError:
            return False
        return any(plate.findall("model_instance") for plate in root.findall("plate"))

    def _build_snapmaker_plate_preserving_package(
        self,
        entries: dict[str, bytes],
        preserve_all_entries: bool = False,
    ) -> tuple[dict[str, bytes], list[str], list[str]]:
        package_entries: dict[str, bytes] = {}
        adapted: list[str] = []
        lost: list[str] = []

        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted, lost

        try:
            if preserve_all_entries:
                package_entries = {name.replace("\\", "/"): data for name, data in entries.items()}
                adapted.append(
                    "Pacote 3MF grande preservado quase integralmente para priorizar fidelidade de plates e resposta operacional."
                )
                return package_entries, adapted, lost

            package_entries[root_key] = entries[root_key]
            for name, data in entries.items():
                normalized = name.replace("\\", "/")
                if normalized == root_key:
                    continue
                if normalized.startswith("Metadata/"):
                    package_entries[normalized] = data
                    continue
                if normalized == "Auxiliaries/.thumbnails/thumbnail_3mf.png":
                    package_entries[normalized] = data

            include_thumbnail = "Auxiliaries/.thumbnails/thumbnail_3mf.png" in package_entries
            package_entries["_rels/.rels"] = self._build_package_relationships_xml(
                include_thumbnail=include_thumbnail
            )
            package_entries["[Content_Types].xml"] = self._build_content_types_xml(
                include_thumbnail=include_thumbnail,
                include_project_settings="Metadata/project_settings.config" in package_entries,
                include_xml_config=True,
                include_json=True,
            )
            adapted.append(
                "Pacote 3MF final preservou a estrutura de plates, metadados e previews originais do projeto Bambu, saneando apenas o necessário para a Snapmaker."
            )
        except Exception as exc:
            lost.append(f"preservacao da estrutura de plates falhou: {exc}")
            return entries, adapted, lost

        return package_entries, adapted, lost

    def _sanitize_project_settings(
        self,
        settings: dict[str, Any],
        support_plan: dict[str, Any] | None = None,
        adhesion_plan: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
        applied: list[str] = []
        equivalence: list[dict[str, Any]] = []

        sentinel_defaults = {
            "raft_first_layer_expansion": 0,
            "tree_support_wall_count": 0,
        }
        for key, fallback in sentinel_defaults.items():
            if key not in settings:
                continue
            original_value = self._parse_int(settings[key])
            if original_value is not None and original_value < 0:
                settings[key] = str(fallback)
                applied.append(f"{key} ajustado de {original_value} para {fallback}")
                equivalence.append(
                    self._equivalence_record(
                        key,
                        original_value,
                        settings[key],
                        "fallback_substitution",
                        "Valor negativo incompatível com o Snapmaker Orca foi normalizado.",
                    )
                )

        for key, value in list(settings.items()):
            if not key.endswith("_filament"):
                continue
            normalized = self._normalize_filament_reference(value)
            if normalized != value:
                settings[key] = normalized
                applied.append(f"{key} remapeado para indice de filamento 1-based compativel")
                equivalence.append(
                    self._equivalence_record(
                        key,
                        value,
                        normalized,
                        "fallback_substitution",
                        "Índice de filamento foi remapeado para extrusor único 1-based.",
                    )
                )

        if self._parse_int(settings.get("use_relative_e_distances")) == 1:
            previous = settings.get("use_relative_e_distances")
            settings["use_relative_e_distances"] = "0"
            applied.append("use_relative_e_distances desativado para compatibilidade com Snapmaker Orca")
            equivalence.append(
                self._equivalence_record(
                    "use_relative_e_distances",
                    previous,
                    "0",
                    "fallback_substitution",
                    "Extrusão relativa foi neutralizada para o fluxo Snapmaker.",
                )
            )

        layer_gcode_keys = ("before_layer_change_gcode", "layer_change_gcode", "layer_gcode")
        for key in layer_gcode_keys:
            current = settings.get(key)
            if not isinstance(current, str):
                continue
            if "G92 E0" not in current:
                continue
            sanitized = "\n".join(line for line in current.splitlines() if line.strip() != "G92 E0").strip()
            settings[key] = sanitized
            applied.append(f"{key} teve G92 E0 removido para compatibilidade com extrusão absoluta da Snapmaker")
            equivalence.append(
                self._equivalence_record(
                    key,
                    current,
                    sanitized,
                    "fallback_substitution",
                    "G92 E0 foi removido do G-code de camada porque o fluxo Snapmaker usa extrusão absoluta.",
                )
            )

        settings, profile_changes, profile_equivalence = self._apply_snapmaker_profile(
            settings,
            support_plan=support_plan,
            adhesion_plan=adhesion_plan,
        )
        applied.extend(profile_changes)
        equivalence.extend(profile_equivalence)

        return settings, applied, equivalence

    def _inline_external_geometry(
        self,
        entries: dict[str, bytes],
    ) -> tuple[dict[str, bytes], list[str], list[str]]:
        adapted: list[str] = []
        lost: list[str] = []
        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted, lost

        try:
            model_docs = {
                self._normalize_model_path(name): ET.fromstring(data)
                for name, data in entries.items()
                if name.lower().endswith(".model")
            }
            root_path = self._normalize_model_path(root_key)
            root_tree = model_docs.get(root_path)
            if root_tree is None:
                return entries, adapted, lost

            root_resources = root_tree.find(self._q("resources"))
            if root_resources is None:
                return entries, adapted, lost

            external_paths = [path for path in model_docs if path != root_path]
            if not external_paths:
                return entries, adapted, lost

            existing_ids = [
                int(child.attrib["id"])
                for child in root_resources
                if child.attrib.get("id", "").isdigit()
            ]
            next_id = max(existing_ids, default=0) + 1
            remap_by_path: dict[str, dict[str, str]] = {}

            for path in external_paths:
                resources = model_docs[path].find(self._q("resources"))
                if resources is None:
                    continue
                resource_map: dict[str, str] = {}
                for child in list(resources):
                    old_id = child.attrib.get("id")
                    if not old_id:
                        continue
                    resource_map[old_id] = str(next_id)
                    next_id += 1
                if resource_map:
                    remap_by_path[path] = resource_map

            if not remap_by_path:
                return entries, adapted, lost

            imported_resources = 0
            for path in external_paths:
                resources = model_docs[path].find(self._q("resources"))
                if resources is None:
                    continue
                for child in list(resources):
                    old_id = child.attrib.get("id")
                    if not old_id:
                        continue
                    clone = copy.deepcopy(child)
                    clone.attrib["id"] = remap_by_path[path][old_id]
                    self._remap_resource_references(clone, path, remap_by_path)
                    root_resources.append(clone)
                    imported_resources += 1

            rewired_components = 0
            for component in root_tree.findall(f".//{self._q('component')}"):
                source_path = component.attrib.get(f"{{{self.PROD_NS}}}path")
                if not source_path:
                    continue
                normalized_path = self._normalize_model_path(source_path)
                mapped_object_id = remap_by_path.get(normalized_path, {}).get(component.attrib.get("objectid", ""))
                if not mapped_object_id:
                    continue
                component.attrib["objectid"] = mapped_object_id
                component.attrib.pop(f"{{{self.PROD_NS}}}path", None)
                rewired_components += 1

            if rewired_components == 0:
                return entries, adapted, lost

            entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)
            adapted.append(
                f"Geometrias externas do 3MF foram embutidas no modelo raiz para compatibilidade com leitores que nao resolvem production refs ({imported_resources} recursos importados, {rewired_components} componentes religados)."
            )
        except Exception as exc:
            lost.append(f"embutir geometria externa no 3MF falhou: {exc}")

        return entries, adapted, lost

    def _finalize_root_only_package(
        self,
        entries: dict[str, bytes],
    ) -> tuple[dict[str, bytes], list[str], list[str]]:
        adapted: list[str] = []
        lost: list[str] = []
        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted, lost

        try:
            root_tree = ET.fromstring(entries[root_key])
            root_has_prod_refs = any(
                f"{{{self.PROD_NS}}}path" in node.attrib
                for node in root_tree.iter()
            )
            if root_has_prod_refs:
                return entries, adapted, lost

            root_tree.attrib.pop("requiredextensions", None)
            for node in root_tree.iter():
                for attr_name in list(node.attrib.keys()):
                    if attr_name.endswith("}path"):
                        node.attrib.pop(attr_name, None)

            entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)

            removed_entries = []
            for name in list(entries.keys()):
                normalized = name.replace("\\", "/")
                if normalized.startswith("3D/Objects/") and normalized.lower().endswith(".model"):
                    entries.pop(name, None)
                    removed_entries.append(name)

            if "3D/_rels/3dmodel.model.rels" in entries:
                entries.pop("3D/_rels/3dmodel.model.rels", None)
                removed_entries.append("3D/_rels/3dmodel.model.rels")

            if removed_entries:
                adapted.append(
                    f"Pacote 3MF foi convertido para modelo autocontido; {len(removed_entries)} partes externas/relations foram removidas."
                )
        except Exception as exc:
            lost.append(f"finalização autocontida do pacote 3MF falhou: {exc}")

        return entries, adapted, lost

    def _bake_build_items_to_direct_meshes(
        self,
        entries: dict[str, bytes],
    ) -> tuple[dict[str, bytes], list[str], list[str]]:
        adapted: list[str] = []
        lost: list[str] = []
        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted, lost

        try:
            root_tree = ET.fromstring(entries[root_key])
            resources = root_tree.find(self._q("resources"))
            build = root_tree.find(self._q("build"))
            if resources is None or build is None:
                return entries, adapted, lost

            objects = resources.findall(self._q("object"))
            if not objects:
                return entries, adapted, lost

            object_index = {obj.attrib.get("id", ""): obj for obj in objects if obj.attrib.get("id")}
            build_items = build.findall(self._q("item"))
            if not build_items:
                return entries, adapted, lost

            new_root = ET.Element(root_tree.tag, dict(root_tree.attrib))
            new_resources = ET.SubElement(new_root, self._q("resources"))
            new_build = ET.SubElement(new_root, self._q("build"))

            for child in list(resources):
                if child.tag != self._q("object"):
                    new_resources.append(copy.deepcopy(child))

            next_id = 1
            baked_count = 0
            for item in build_items:
                object_id = item.attrib.get("objectid")
                if not object_id:
                    continue

                fragments: list[tuple[ET.Element, list[list[float]]]] = []
                self._collect_mesh_fragments(
                    object_index=object_index,
                    object_id=object_id,
                    matrix=self._parse_transform(item.attrib.get("transform")),
                    fragments=fragments,
                    visited=set(),
                )
                if not fragments:
                    lost.append(f"Item de build {object_id} nao gerou malha bakeada.")
                    continue

                baked_object = ET.Element(
                    self._q("object"),
                    {
                        "id": str(next_id),
                        "type": "model",
                    },
                )
                source_object = object_index.get(object_id)
                if source_object is not None:
                    for child in list(source_object):
                        if child.tag in {self._q("mesh"), self._q("components")}:
                            continue
                        baked_object.append(copy.deepcopy(child))

                mesh = ET.SubElement(baked_object, self._q("mesh"))
                vertices = ET.SubElement(mesh, self._q("vertices"))
                triangles = ET.SubElement(mesh, self._q("triangles"))

                vertex_offset = 0
                for fragment_object, fragment_matrix in fragments:
                    fragment_mesh = fragment_object.find(self._q("mesh"))
                    if fragment_mesh is None:
                        continue
                    fragment_vertices = fragment_mesh.find(self._q("vertices"))
                    fragment_triangles = fragment_mesh.find(self._q("triangles"))
                    if fragment_vertices is None or fragment_triangles is None:
                        continue

                    fragment_vertex_nodes = fragment_vertices.findall(self._q("vertex"))
                    for vertex in fragment_vertex_nodes:
                        x = float(vertex.attrib.get("x", 0.0))
                        y = float(vertex.attrib.get("y", 0.0))
                        z = float(vertex.attrib.get("z", 0.0))
                        tx, ty, tz = self._apply_transform_to_point(fragment_matrix, x, y, z)
                        ET.SubElement(
                            vertices,
                            self._q("vertex"),
                            {
                                "x": f"{tx:.9g}",
                                "y": f"{ty:.9g}",
                                "z": f"{tz:.9g}",
                            },
                        )

                    for triangle in fragment_triangles.findall(self._q("triangle")):
                        attrs = dict(triangle.attrib)
                        attrs["v1"] = str(int(attrs["v1"]) + vertex_offset)
                        attrs["v2"] = str(int(attrs["v2"]) + vertex_offset)
                        attrs["v3"] = str(int(attrs["v3"]) + vertex_offset)
                        ET.SubElement(triangles, self._q("triangle"), attrs)

                    vertex_offset += len(fragment_vertex_nodes)

                if vertex_offset == 0 or not triangles.findall(self._q("triangle")):
                    lost.append(f"Item de build {object_id} resultou em malha vazia apos bake.")
                    continue

                new_resources.append(baked_object)

                item_attrs = {key: value for key, value in item.attrib.items() if key not in {"objectid", "transform"}}
                item_attrs["objectid"] = str(next_id)
                ET.SubElement(new_build, self._q("item"), item_attrs)
                next_id += 1
                baked_count += 1

            if baked_count == 0:
                lost.append("Nenhum item de build pode ser convertido para malha direta.")
                return entries, adapted, lost

            entries[root_key] = ET.tostring(new_root, encoding="utf-8", xml_declaration=True)
            adapted.append(
                f"Geometria do build foi bakeada em {baked_count} malhas diretas para compatibilidade máxima com Snapmaker Orca."
            )
        except Exception as exc:
            lost.append(f"bake de build items para malhas diretas falhou: {exc}")

        return entries, adapted, lost

    def _collect_mesh_fragments(
        self,
        *,
        object_index: dict[str, ET.Element],
        object_id: str,
        matrix: list[list[float]],
        fragments: list[tuple[ET.Element, list[list[float]]]],
        visited: set[str],
    ) -> None:
        if object_id in visited:
            return
        visited.add(object_id)

        obj = object_index.get(object_id)
        if obj is None:
            return

        mesh = obj.find(self._q("mesh"))
        if mesh is not None:
            fragments.append((obj, matrix))
            return

        components = obj.find(self._q("components"))
        if components is None:
            return

        for component in components.findall(self._q("component")):
            component_id = component.attrib.get("objectid")
            if not component_id:
                continue
            component_matrix = self._parse_transform(component.attrib.get("transform"))
            self._collect_mesh_fragments(
                object_index=object_index,
                object_id=component_id,
                matrix=self._multiply_matrices(matrix, component_matrix),
                fragments=fragments,
                visited=set(visited),
            )

    def _apply_transform_to_point(
        self,
        matrix: list[list[float]],
        x: float,
        y: float,
        z: float,
    ) -> tuple[float, float, float]:
        tx = (matrix[0][0] * x) + (matrix[0][1] * y) + (matrix[0][2] * z) + matrix[0][3]
        ty = (matrix[1][0] * x) + (matrix[1][1] * y) + (matrix[1][2] * z) + matrix[1][3]
        tz = (matrix[2][0] * x) + (matrix[2][1] * y) + (matrix[2][2] * z) + matrix[2][3]
        return tx, ty, tz

    def _build_snapmaker_safe_package(
        self,
        entries: dict[str, bytes],
    ) -> tuple[dict[str, bytes], list[str]]:
        minimal_entries: dict[str, bytes] = {}
        adapted: list[str] = []

        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted

        minimal_entries[root_key] = entries[root_key]
        if "Metadata/project_settings.config" in entries:
            minimal_entries["Metadata/project_settings.config"] = entries["Metadata/project_settings.config"]
        if "Auxiliaries/.thumbnails/thumbnail_3mf.png" in entries:
            minimal_entries["Auxiliaries/.thumbnails/thumbnail_3mf.png"] = entries["Auxiliaries/.thumbnails/thumbnail_3mf.png"]

        minimal_entries["_rels/.rels"] = self._build_package_relationships_xml(
            include_thumbnail="Auxiliaries/.thumbnails/thumbnail_3mf.png" in minimal_entries
        )
        minimal_entries["[Content_Types].xml"] = self._build_content_types_xml(
            include_thumbnail="Auxiliaries/.thumbnails/thumbnail_3mf.png" in minimal_entries,
            include_project_settings="Metadata/project_settings.config" in minimal_entries,
        )
        adapted.append("Pacote 3MF final foi reempacotado em formato mínimo compatível com Snapmaker Orca.")
        return minimal_entries, adapted

    def _build_package_relationships_xml(self, *, include_thumbnail: bool) -> bytes:
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '  <Relationship Target="3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>',
        ]
        if include_thumbnail:
            lines.append(
                '  <Relationship Target="Auxiliaries/.thumbnails/thumbnail_3mf.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>'
            )
        lines.append("</Relationships>")
        return "\n".join(lines).encode("utf-8")

    def _build_content_types_xml(
        self,
        *,
        include_thumbnail: bool,
        include_project_settings: bool,
        include_xml_config: bool = False,
        include_json: bool = False,
    ) -> bytes:
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>',
        ]
        if include_thumbnail:
            lines.append('  <Default Extension="png" ContentType="image/png"/>')
        if include_json:
            lines.append('  <Default Extension="json" ContentType="application/json"/>')
        if include_xml_config:
            lines.append('  <Default Extension="xml" ContentType="application/xml"/>')
        if include_project_settings:
            lines.append('  <Default Extension="config" ContentType="application/json"/>')
        lines.append("</Types>")
        return "\n".join(lines).encode("utf-8")

    def _fit_root_meshes_within_plate(
        self,
        entries: dict[str, bytes],
    ) -> tuple[dict[str, bytes], list[str], list[str]]:
        adapted: list[str] = []
        lost: list[str] = []
        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted, lost

        try:
            root_tree = ET.fromstring(entries[root_key])
            vertex_nodes = list(root_tree.findall(f".//{self._q('vertex')}"))
            if not vertex_nodes:
                return entries, adapted, lost

            xs = [float(vertex.attrib.get("x", 0.0)) for vertex in vertex_nodes]
            ys = [float(vertex.attrib.get("y", 0.0)) for vertex in vertex_nodes]
            zs = [float(vertex.attrib.get("z", 0.0)) for vertex in vertex_nodes]

            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            min_z = min(zs)

            bed_x = float(self.settings.snapmaker_build_volume_x_mm)
            bed_y = float(self.settings.snapmaker_build_volume_y_mm)
            margin = 5.0
            usable_x = max(bed_x - (2 * margin), 1.0)
            usable_y = max(bed_y - (2 * margin), 1.0)
            extent_x = max_x - min_x
            extent_y = max_y - min_y

            scale_factor = 1.0
            if extent_x > usable_x or extent_y > usable_y:
                scale_factor = min(usable_x / max(extent_x, 1e-9), usable_y / max(extent_y, 1e-9))

            scaled_min_x = min_x * scale_factor
            scaled_max_x = max_x * scale_factor
            scaled_min_y = min_y * scale_factor
            scaled_max_y = max_y * scale_factor
            scaled_min_z = min_z * scale_factor
            scaled_extent_x = scaled_max_x - scaled_min_x
            scaled_extent_y = scaled_max_y - scaled_min_y

            translate_x = margin + ((usable_x - scaled_extent_x) / 2.0) - scaled_min_x
            translate_y = margin + ((usable_y - scaled_extent_y) / 2.0) - scaled_min_y
            translate_z = -scaled_min_z

            for vertex in vertex_nodes:
                x = float(vertex.attrib.get("x", 0.0)) * scale_factor
                y = float(vertex.attrib.get("y", 0.0)) * scale_factor
                z = float(vertex.attrib.get("z", 0.0)) * scale_factor
                vertex.attrib["x"] = f"{x + translate_x:.9g}"
                vertex.attrib["y"] = f"{y + translate_y:.9g}"
                vertex.attrib["z"] = f"{z + translate_z:.9g}"

            entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)
            if scale_factor < 0.999999:
                adapted.append(
                    f"Geometria foi reescalada em {scale_factor:.4f} para manter todo o percurso dentro da mesa da Snapmaker U1."
                )
            adapted.append("Geometria final foi recentralizada e assentada dentro da área útil da mesa.")
        except Exception as exc:
            lost.append(f"ajuste final da geometria para a mesa falhou: {exc}")

        return entries, adapted, lost

    def _flatten_composite_build_items(
        self,
        entries: dict[str, bytes],
    ) -> tuple[dict[str, bytes], list[str], list[str]]:
        adapted: list[str] = []
        lost: list[str] = []
        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, adapted, lost

        try:
            model_docs = {
                self._normalize_model_path(name): ET.fromstring(data)
                for name, data in entries.items()
                if name.lower().endswith(".model")
            }
            root_path = self._normalize_model_path(root_key)
            root_tree = model_docs.get(root_path)
            if root_tree is None:
                return entries, adapted, lost

            build = root_tree.find(self._q("build"))
            if build is None:
                return entries, adapted, lost

            original_items = list(build.findall(self._q("item")))
            if not original_items:
                return entries, adapted, lost

            flattened_items: list[ET.Element] = []
            flattened_count = 0
            changed = False
            for item in original_items:
                object_id = item.attrib.get("objectid")
                if not object_id:
                    continue
                item_matrix = self._parse_transform(item.attrib.get("transform"))
                printable = item.attrib.get("printable", "1")
                leaf_refs = self._expand_to_leaf_meshes(root_path, object_id, model_docs)
                if not leaf_refs:
                    flattened_items.append(copy.deepcopy(item))
                    continue
                if len(leaf_refs) == 1 and leaf_refs[0]["object_id"] == object_id:
                    flattened_items.append(copy.deepcopy(item))
                    continue
                changed = True
                for leaf in leaf_refs:
                    flattened_count += 1
                    combined = self._multiply_matrices(item_matrix, leaf["matrix"])
                    new_item = ET.Element(self._q("item"))
                    new_item.set("objectid", leaf["object_id"])
                    new_item.set("transform", self._format_transform(combined))
                    new_item.set("printable", printable)
                    flattened_items.append(new_item)

            if not changed:
                return entries, adapted, lost

            for candidate in list(build.findall(self._q("item"))):
                build.remove(candidate)
            for item in flattened_items:
                build.append(item)

            entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)
            adapted.append(
                f"Objetos compostos do build foram achatados em {flattened_count} itens de malha direta para compatibilidade com o Snapmaker Orca."
            )
        except Exception as exc:
            lost.append(f"achatamento de objetos compostos do build falhou: {exc}")

        return entries, adapted, lost

    def _apply_snapmaker_profile(
        self,
        settings: dict[str, Any],
        support_plan: dict[str, Any] | None = None,
        adhesion_plan: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
        applied: list[str] = []
        equivalence: list[dict[str, Any]] = []
        support_plan = support_plan or {"enabled": False}
        adhesion_plan = adhesion_plan or {"mode": "skirt"}
        support_enabled = bool(support_plan.get("enabled"))
        adhesion_mode = str(adhesion_plan.get("mode", "skirt"))
        adhesion_uses_raft = adhesion_mode == "raft"
        adhesion_uses_brim = adhesion_mode == "brim"
        brim_width = str(adhesion_plan.get("brim_width_mm", 0 if not adhesion_uses_brim else 6))
        raft_layers = str(adhesion_plan.get("raft_layers", 2 if adhesion_uses_raft else 0))
        initial_layer_speed = str(adhesion_plan.get("initial_layer_speed_mm_s", 30))
        initial_layer_infill_speed = str(adhesion_plan.get("initial_layer_infill_speed_mm_s", 30))
        initial_layer_acceleration = str(adhesion_plan.get("initial_layer_acceleration_mm_s2", 500))
        initial_layer_flow_ratio = str(adhesion_plan.get("initial_layer_flow_ratio", 1.0))
        initial_layer_height = str(adhesion_plan.get("initial_layer_height_mm", 0.2))

        replacements: dict[str, Any] = {
            "printer_model": self.SNAPMAKER_PROFILE_NAME,
            "printer_settings_id": self.SNAPMAKER_PROFILE_NAME,
            "printer_structure": "cartesian",
            "printer_technology": "FFF",
            "printer_variant": "0.4",
            "gcode_flavor": "marlin",
            "machine_start_gcode": self.SNAPMAKER_START_GCODE,
            "machine_end_gcode": self.SNAPMAKER_END_GCODE,
            "change_filament_gcode": "",
            "time_lapse_gcode": "",
            "machine_pause_gcode": "M0",
            "before_layer_change_gcode": "",
            "layer_change_gcode": self.SNAPMAKER_LAYER_CHANGE_GCODE,
            "single_extruder_multi_material": "0",
            "use_relative_e_distances": "0",
            "curr_bed_type": "Smooth PEI Plate",
            "template_custom_gcode": "",
            "printing_by_object_gcode": "",
            "wrapping_detection_gcode": "",
            "master_extruder_id": "1",
            "enable_prime_tower": "0",
            "enable_tower_interface_features": "0",
            "flush_into_infill": "0",
            "flush_into_objects": "0",
            "flush_into_support": "0",
            "prime_tower_enable_framework": "0",
            "prime_tower_extra_rib_length": "0",
            "prime_tower_fillet_wall": "0",
            "prime_tower_flat_ironing": "0",
            "prime_tower_lift_height": "0",
            "prime_tower_lift_speed": "0",
            "prime_tower_max_speed": "0",
            "prime_tower_rib_wall": "0",
            "prime_tower_rib_width": "0",
            "prime_tower_skip_points": "0",
            "prime_tower_width": "2",
            "prime_tower_brim_width": "0",
            "prime_volume_mode": "None",
            "raft_first_layer_expansion": "0",
            "role_base_wipe_speed": "0",
            "support_object_skip_flush": "1",
            "wipe_tower_no_sparse_layers": "0",
            "wipe_tower_rotation_angle": "0",
            "enable_support": "1" if support_enabled else "0",
            "support_type": support_plan.get("type", "tree(auto)") if support_enabled else "normal(auto)",
            "support_style": "default",
            "support_threshold_angle": str(support_plan.get("threshold_angle", 25 if support_enabled else 30)),
            "support_on_build_plate_only": "1" if support_enabled else "0",
            "support_remove_small_overhang": "0" if support_enabled else "1",
            "support_interface_top_layers": "2" if support_enabled else "0",
            "support_interface_bottom_layers": "2" if support_enabled else "0",
            "support_object_xy_distance": "0.35" if support_enabled else "0.4",
            "support_top_z_distance": "0.2" if support_enabled else "0.22",
            "support_bottom_z_distance": "0.2" if support_enabled else "0.22",
            "brim_type": "auto_brim" if adhesion_uses_brim else "no_brim",
            "brim_width": brim_width,
            "brim_object_gap": "0.05" if adhesion_uses_brim else "0.1",
            "skirt_loops": "1" if adhesion_uses_raft else str(adhesion_plan.get("skirt_loops", 2)),
            "skirt_distance": "2",
            "skirt_height": "1",
            "raft_layers": raft_layers,
            "raft_contact_distance": "0.1",
            "raft_expansion": "1.5",
            "raft_first_layer_density": "90%",
            "initial_layer_flow_ratio": initial_layer_flow_ratio,
            "initial_layer_line_width": "0.5",
            "initial_layer_print_height": initial_layer_height,
            "initial_layer_jerk": "7",
            "draft_shield": "disabled",
            "best_object_pos": "0.5,0.5",
        }

        for key, value in replacements.items():
            previous = settings.get(key)
            if previous != value:
                settings[key] = value
                applied.append(f"{key} substituido por perfil Snapmaker/Marlin seguro")
                equivalence.append(
                    self._equivalence_record(
                        key,
                        previous,
                        value,
                        "fallback_substitution",
                        "Parâmetro substituído pelo perfil central seguro da Snapmaker U1.",
                    )
                )

        single_printer_array = [self.SNAPMAKER_PROFILE_NAME]
        list_replacements: dict[str, Any] = {
            "print_compatible_printers": single_printer_array,
            "upward_compatible_machine": single_printer_array,
            "print_extruder_id": ["1"],
            "printer_extruder_id": ["1"],
            "print_extruder_variant": ["Direct Drive Standard"],
            "printer_extruder_variant": ["Direct Drive Standard"],
            "extruder_colour": ["#F97316"],
            "extruder_type": ["Direct Drive"],
            "extruder_max_nozzle_count": ["1"],
            "extruder_nozzle_stats": ["Standard#1"],
            "extruder_variant_list": ["Direct Drive Standard"],
            "physical_extruder_map": ["0"],
            "machine_max_acceleration_e": ["1500"],
            "machine_max_acceleration_extruding": ["3000"],
            "machine_max_acceleration_retracting": ["1500"],
            "machine_max_acceleration_travel": ["5000"],
            "machine_max_acceleration_x": ["3000"],
            "machine_max_acceleration_y": ["3000"],
            "machine_max_acceleration_z": ["100"],
            "machine_max_jerk_e": ["2.0"],
            "machine_max_jerk_x": ["8"],
            "machine_max_jerk_y": ["8"],
            "machine_max_jerk_z": ["0.4"],
            "machine_max_speed_e": ["25"],
            "machine_max_speed_x": ["250"],
            "machine_max_speed_y": ["250"],
            "machine_max_speed_z": ["10"],
            "machine_min_extruding_rate": ["0"],
            "machine_min_travel_rate": ["0"],
            "filament_start_gcode": [self.SNAPMAKER_FILAMENT_START_GCODE],
            "filament_end_gcode": [self.SNAPMAKER_FILAMENT_END_GCODE],
            "printable_area": [
                f"0x0",
                f"{int(self.settings.snapmaker_build_volume_x_mm)}x0",
                f"{int(self.settings.snapmaker_build_volume_x_mm)}x{int(self.settings.snapmaker_build_volume_y_mm)}",
                f"0x{int(self.settings.snapmaker_build_volume_y_mm)}",
            ],
            "plate_shape": [
                f"0x0",
                f"{int(self.settings.snapmaker_build_volume_x_mm)}x0",
                f"{int(self.settings.snapmaker_build_volume_x_mm)}x{int(self.settings.snapmaker_build_volume_y_mm)}",
                f"0x{int(self.settings.snapmaker_build_volume_y_mm)}",
            ],
            "bed_exclude_area": [],
            "initial_layer_speed": [initial_layer_speed],
            "initial_layer_infill_speed": [initial_layer_infill_speed],
            "initial_layer_acceleration": [initial_layer_acceleration],
            "initial_layer_travel_acceleration": ["3000"],
            "wipe": ["0"],
            "wipe_distance": ["0"],
            "retract_before_wipe": ["0"],
            "filament_wipe": ["0"],
            "filament_wipe_distance": ["0"],
            "filament_retract_before_wipe": ["0"],
            "filament_prime_volume": ["0"],
            "filament_prime_volume_nc": ["0"],
            "filament_minimal_purge_on_wipe_tower": ["0"],
            "filament_tower_interface_pre_extrusion_dist": ["0"],
            "filament_tower_interface_pre_extrusion_length": ["0"],
            "filament_tower_interface_print_temp": ["0"],
            "filament_tower_interface_purge_volume": ["0"],
            "filament_tower_ironing_area": ["0"],
            "filament_cooling_before_tower": ["0"],
            "filament_flush_temp": ["0"],
            "filament_flush_volumetric_speed": ["0"],
            "flush_multiplier": ["0"],
            "flush_volumes_matrix": ["0"],
            "flush_volumes_vector": ["0"],
            "nozzle_flush_dataset": ["0"],
            "wipe_tower_x": ["0"],
            "wipe_tower_y": ["0"],
        }

        for key, value in list_replacements.items():
            previous = settings.get(key)
            if previous != value:
                settings[key] = value
                applied.append(f"{key} normalizado para perfil de extrusor unico Snapmaker")
                equivalence.append(
                    self._equivalence_record(
                        key,
                        previous,
                        value,
                        "preserved_approximately",
                        "Lista normalizada para o fluxo de extrusor único da Snapmaker.",
                    )
                )

        removable_prefixes = (
            "filament_dev_ams_",
            "extruder_ams_",
        )
        removable_keys = {
            "machine_hotend_change_time",
            "machine_load_filament_time",
            "machine_unload_filament_time",
            "timelapse_type",
        }
        for key in list(settings.keys()):
            if key in removable_keys or key.startswith(removable_prefixes):
                previous = settings.get(key)
                settings.pop(key, None)
                applied.append(f"{key} removido por ser especifico do fluxo Bambu/AMS")
                equivalence.append(
                    self._equivalence_record(
                        key,
                        previous,
                        None,
                        "discarded_incompatible",
                        "Parâmetro proprietário do ecossistema Bambu/AMS sem equivalência segura.",
                    )
                )

        return settings, applied, equivalence

    def _equivalence_record(
        self,
        parameter: str,
        source_value: Any,
        target_value: Any,
        status: str,
        note: str,
    ) -> dict[str, Any]:
        return {
            "parameter": parameter,
            "source_value": source_value,
            "target_value": target_value,
            "status": status,
            "note": note,
        }

    def _normalize_filament_reference(self, value: Any) -> Any:
        if isinstance(value, list):
            normalized_list = [self._normalize_filament_reference(item) for item in value]
            return normalized_list if normalized_list != value else value

        parsed = self._parse_int(value)
        if parsed is None:
            return value
        if parsed <= 0:
            return "1"
        return str(parsed)

    def _parse_int(self, value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("-") and stripped[1:].isdigit():
                return int(stripped)
            if stripped.isdigit():
                return int(stripped)
        return None

    def _expand_to_leaf_meshes(
        self,
        model_path: str,
        object_id: str,
        model_docs: dict[str, ET.Element],
        inherited_matrix: list[list[float]] | None = None,
    ) -> list[dict[str, Any]]:
        matrix = inherited_matrix or self._identity_matrix()
        model_root = model_docs.get(model_path)
        if model_root is None:
            return []

        resources = model_root.find(self._q("resources"))
        if resources is None:
            return []

        for obj in resources.findall(self._q("object")):
            if obj.attrib.get("id") != str(object_id):
                continue
            if obj.find(self._q("mesh")) is not None:
                return [{"object_id": str(object_id), "matrix": matrix}]

            components = obj.find(self._q("components"))
            if components is None:
                return []

            expanded: list[dict[str, Any]] = []
            for component in components.findall(self._q("component")):
                child_object_id = component.attrib.get("objectid")
                if not child_object_id:
                    continue
                child_path = component.attrib.get(f"{{{self.PROD_NS}}}path")
                resolved_model_path = self._normalize_model_path(child_path) if child_path else model_path
                child_matrix = self._multiply_matrices(matrix, self._parse_transform(component.attrib.get("transform")))
                expanded.extend(
                    self._expand_to_leaf_meshes(
                        resolved_model_path,
                        child_object_id,
                        model_docs,
                        child_matrix,
                    )
                )
            return expanded

        return []

    def _remap_resource_references(
        self,
        element: ET.Element,
        current_model_path: str,
        remap_by_path: dict[str, dict[str, str]],
    ) -> None:
        local_map = remap_by_path.get(current_model_path, {})

        for node in element.iter():
            if node.attrib.get("objectid"):
                source_path = node.attrib.get(f"{{{self.PROD_NS}}}path")
                if source_path:
                    normalized_path = self._normalize_model_path(source_path)
                    mapped = remap_by_path.get(normalized_path, {}).get(node.attrib["objectid"])
                    if mapped:
                        node.attrib["objectid"] = mapped
                        node.attrib.pop(f"{{{self.PROD_NS}}}path", None)
                elif node.attrib["objectid"] in local_map:
                    node.attrib["objectid"] = local_map[node.attrib["objectid"]]

            for resource_attr in ("pid", "texid"):
                original = node.attrib.get(resource_attr)
                if original and original in local_map:
                    node.attrib[resource_attr] = local_map[original]

    def _normalize_and_split_layout(
        self,
        entries: dict[str, bytes],
        scale_mode: str | None = None,
    ) -> tuple[dict[str, bytes], list[bytes], list[str], list[str]]:
        adapted: list[str] = []
        lost: list[str] = []
        extra_root_models: list[bytes] = []
        root_key = "3D/3dmodel.model"
        if root_key not in entries:
            return entries, extra_root_models, adapted, lost

        try:
            model_docs = {
                self._normalize_model_path(name): ET.fromstring(data)
                for name, data in entries.items()
                if name.lower().endswith(".model")
            }
            root_path = self._normalize_model_path(root_key)
            root_tree = model_docs[root_path]
            build = root_tree.find(self._q("build"))
            if build is None:
                return entries, extra_root_models, adapted, lost

            items = build.findall(self._q("item"))
            if not items:
                return entries, extra_root_models, adapted, lost

            cache: dict[tuple[str, str], tuple[list[float], list[float]] | None] = {}
            bed_x = float(self.settings.snapmaker_build_volume_x_mm)
            bed_y = float(self.settings.snapmaker_build_volume_y_mm)
            margin = 5.0

            item_layouts: list[dict[str, Any]] = []
            for item in items:
                object_id = item.attrib.get("objectid")
                if not object_id:
                    continue
                local_bounds = self._compute_object_bounds(root_path, object_id, model_docs, cache)
                if local_bounds is None:
                    continue
                matrix = self._parse_transform(item.attrib.get("transform"))
                world_bounds = self._transform_bounds(local_bounds, matrix)
                matrix[2][3] -= world_bounds[0][2]
                grounded_bounds = self._transform_bounds(local_bounds, matrix)
                item_layouts.append(
                    {
                        "item": item,
                        "local_bounds": local_bounds,
                        "matrix": matrix,
                        "bounds": grounded_bounds,
                    }
                )

            if not item_layouts:
                return entries, extra_root_models, adapted, lost

            overall_bounds = self._combine_bounds(layout["bounds"] for layout in item_layouts)
            if overall_bounds is None:
                return entries, extra_root_models, adapted, lost

            overall_size_x = overall_bounds[1][0] - overall_bounds[0][0]
            overall_size_y = overall_bounds[1][1] - overall_bounds[0][1]
            overall_size_z = overall_bounds[1][2] - overall_bounds[0][2]
            combined_fits = (
                overall_size_x <= (bed_x - 2 * margin)
                and overall_size_y <= (bed_y - 2 * margin)
                and overall_size_z <= self.settings.snapmaker_build_volume_z_mm
            )

            if not combined_fits and scale_mode == "fit_to_bed":
                max_x = max(bed_x - 2 * margin, 1.0)
                max_y = max(bed_y - 2 * margin, 1.0)
                max_z = max(float(self.settings.snapmaker_build_volume_z_mm) - 2.0, 1.0)
                factors = []
                if overall_size_x > 0:
                    factors.append(max_x / overall_size_x)
                if overall_size_y > 0:
                    factors.append(max_y / overall_size_y)
                if overall_size_z > 0:
                    factors.append(max_z / overall_size_z)
                fit_factor = min(factors) if factors else 1.0
                if fit_factor < 1.0:
                    applied_factor = fit_factor * 0.97
                    for layout in item_layouts:
                        layout["matrix"] = self._scale_matrix(layout["matrix"], applied_factor)
                        layout["bounds"] = self._transform_bounds(layout["local_bounds"], layout["matrix"])
                    overall_bounds = self._combine_bounds(layout["bounds"] for layout in item_layouts)
                    overall_size_x = overall_bounds[1][0] - overall_bounds[0][0]
                    overall_size_y = overall_bounds[1][1] - overall_bounds[0][1]
                    overall_size_z = overall_bounds[1][2] - overall_bounds[0][2]
                    combined_fits = (
                        overall_size_x <= (bed_x - 2 * margin)
                        and overall_size_y <= (bed_y - 2 * margin)
                        and overall_size_z <= self.settings.snapmaker_build_volume_z_mm
                    )
                    adapted.append(
                        f"Build 3MF foi escalado uniformemente em {applied_factor:.4f} para caber no envelope útil da Snapmaker."
                    )

            if combined_fits:
                dx = (bed_x / 2.0) - ((overall_bounds[0][0] + overall_bounds[1][0]) / 2.0)
                dy = (bed_y / 2.0) - ((overall_bounds[0][1] + overall_bounds[1][1]) / 2.0)
                for layout in item_layouts:
                    layout["matrix"][0][3] += dx
                    layout["matrix"][1][3] += dy
                    layout["item"].set("transform", self._format_transform(layout["matrix"]))
                entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)
                adapted.append("Layout do build foi normalizado para pousar em Z=0 e centralizado na mesa da Snapmaker.")
                return entries, extra_root_models, adapted, lost

            if len(item_layouts) > 1:
                dx = (bed_x / 2.0) - ((overall_bounds[0][0] + overall_bounds[1][0]) / 2.0)
                dy = (bed_y / 2.0) - ((overall_bounds[0][1] + overall_bounds[1][1]) / 2.0)
                for layout in item_layouts:
                    layout["matrix"][0][3] += dx
                    layout["matrix"][1][3] += dy
                    layout["item"].set("transform", self._format_transform(layout["matrix"]))
                entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)
                adapted.append("Layout multipartes foi mantido em um único 3MF final e recentralizado na mesa da Snapmaker.")
                lost.append("O conjunto ainda pode exceder a área útil da Snapmaker e exigir escala ou divisão manual confirmada pelo usuário.")
                return entries, extra_root_models, adapted, lost

            single_layout = item_layouts[0]
            dx = (bed_x / 2.0) - ((single_layout["bounds"][0][0] + single_layout["bounds"][1][0]) / 2.0)
            dy = (bed_y / 2.0) - ((single_layout["bounds"][0][1] + single_layout["bounds"][1][1]) / 2.0)
            single_layout["matrix"][0][3] += dx
            single_layout["matrix"][1][3] += dy
            single_layout["item"].set("transform", self._format_transform(single_layout["matrix"]))
            entries[root_key] = ET.tostring(root_tree, encoding="utf-8", xml_declaration=True)
            adapted.append("Objeto unico foi assentado em Z=0 e centralizado na mesa, mesmo excedendo o envelope configurado.")
            lost.append("Modelo continua maior do que o envelope da Snapmaker e exigira escala ou divisao manual.")
        except Exception as exc:
            lost.append(f"normalizacao automatica do layout 3MF falhou: {exc}")

        return entries, extra_root_models, adapted, lost

    def _compute_object_bounds(
        self,
        model_path: str,
        object_id: str,
        model_docs: dict[str, ET.Element],
        cache: dict[tuple[str, str], tuple[list[float], list[float]] | None],
    ) -> tuple[list[float], list[float]] | None:
        cache_key = (model_path, object_id)
        if cache_key in cache:
            return cache[cache_key]

        model_root = model_docs.get(model_path)
        if model_root is None:
            cache[cache_key] = None
            return None

        for obj in model_root.findall(f"{self._q('resources')}/{self._q('object')}"):
            if obj.attrib.get("id") != str(object_id):
                continue
            mesh = obj.find(self._q("mesh"))
            if mesh is not None:
                vertices = mesh.find(self._q("vertices"))
                coords: list[tuple[float, float, float]] = []
                if vertices is not None:
                    for vertex in vertices.findall(self._q("vertex")):
                        coords.append(
                            (
                                float(vertex.attrib.get("x", "0")),
                                float(vertex.attrib.get("y", "0")),
                                float(vertex.attrib.get("z", "0")),
                            )
                        )
                if coords:
                    xs, ys, zs = zip(*coords)
                    result = ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
                    cache[cache_key] = result
                    return result

            components = obj.find(self._q("components"))
            if components is not None:
                component_bounds: list[tuple[list[float], list[float]]] = []
                for component in components.findall(self._q("component")):
                    child_path = component.attrib.get(f"{{{self.PROD_NS}}}path")
                    resolved_model_path = self._normalize_model_path(child_path) if child_path else model_path
                    child_object_id = component.attrib.get("objectid", "")
                    child_bounds = self._compute_object_bounds(resolved_model_path, child_object_id, model_docs, cache)
                    if child_bounds is None:
                        continue
                    child_matrix = self._parse_transform(component.attrib.get("transform"))
                    component_bounds.append(self._transform_bounds(child_bounds, child_matrix))
                result = self._combine_bounds(component_bounds)
                cache[cache_key] = result
                return result

        cache[cache_key] = None
        return None

    def _transform_bounds(
        self,
        bounds: tuple[list[float], list[float]],
        matrix: list[list[float]],
    ) -> tuple[list[float], list[float]]:
        mins, maxs = bounds
        corners = [
            (x, y, z)
            for x in (mins[0], maxs[0])
            for y in (mins[1], maxs[1])
            for z in (mins[2], maxs[2])
        ]
        transformed = [self._transform_point(corner, matrix) for corner in corners]
        xs, ys, zs = zip(*transformed)
        return ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])

    def _transform_point(self, point: tuple[float, float, float], matrix: list[list[float]]) -> tuple[float, float, float]:
        x, y, z = point
        return (
            matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
            matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
            matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
        )

    def _combine_bounds(
        self,
        bounds_iterable: Any,
    ) -> tuple[list[float], list[float]] | None:
        bounds_list = [bounds for bounds in bounds_iterable if bounds is not None]
        if not bounds_list:
            return None
        mins = [min(bounds[0][axis] for bounds in bounds_list) for axis in range(3)]
        maxs = [max(bounds[1][axis] for bounds in bounds_list) for axis in range(3)]
        return (mins, maxs)

    def _parse_transform(self, value: str | None) -> list[list[float]]:
        if not value:
            return [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        parts = [float(part) for part in value.split()]
        if len(parts) != 12:
            return [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        return [
            [parts[0], parts[1], parts[2], parts[9]],
            [parts[3], parts[4], parts[5], parts[10]],
            [parts[6], parts[7], parts[8], parts[11]],
            [0.0, 0.0, 0.0, 1.0],
        ]

    def _identity_matrix(self) -> list[list[float]]:
        return [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]

    def _multiply_matrices(self, left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
        result = [[0.0] * 4 for _ in range(4)]
        for row in range(4):
            for col in range(4):
                result[row][col] = sum(left[row][idx] * right[idx][col] for idx in range(4))
        return result

    def _format_transform(self, matrix: list[list[float]]) -> str:
        values = [
            matrix[0][0],
            matrix[0][1],
            matrix[0][2],
            matrix[1][0],
            matrix[1][1],
            matrix[1][2],
            matrix[2][0],
            matrix[2][1],
            matrix[2][2],
            matrix[0][3],
            matrix[1][3],
            matrix[2][3],
        ]
        return " ".join(f"{value:.9g}" for value in values)

    def _scale_matrix(self, matrix: list[list[float]], factor: float) -> list[list[float]]:
        scaled = [row[:] for row in matrix]
        for row in range(3):
            for col in range(3):
                scaled[row][col] *= factor
            scaled[row][3] *= factor
        return scaled

    def _normalize_model_path(self, path: str | None) -> str:
        normalized = (path or "3D/3dmodel.model").replace("\\", "/").lstrip("/")
        return normalized

    def _q(self, tag: str) -> str:
        return f"{{{self.CORE_NS}}}{tag}"

    def _write_archive(self, destination: Path, entries: dict[str, bytes]) -> None:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
