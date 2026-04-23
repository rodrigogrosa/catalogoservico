from __future__ import annotations

from pathlib import Path
from typing import Any
import zipfile
import json
from xml.etree import ElementTree as ET

from app.services.snapmaker_profile_service import SnapmakerProfileService


class SlicerValidationService:
    def __init__(self) -> None:
        self.profile_service = SnapmakerProfileService()

    def validate_project_export(self, file_path: Path) -> dict[str, Any]:
        findings: list[str] = []
        risks: list[str] = []
        estimates: dict[str, Any] = {}

        if file_path.suffix.lower() != ".3mf" or not zipfile.is_zipfile(file_path):
            return {
                "status": "skipped",
                "findings": ["Validação operacional detalhada está focada em exportações 3MF para Snapmaker Orca."],
                "risks": [],
                "estimates": {},
            }

        with zipfile.ZipFile(file_path) as archive:
            names = archive.namelist()
            if "Metadata/project_settings.config" not in names:
                risks.append("Export 3MF sem project_settings.config; validação de slicer fica incompleta.")
                settings = {}
            else:
                settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))
            root = ET.fromstring(archive.read("3D/3dmodel.model")) if "3D/3dmodel.model" in names else None

        profile = self.profile_service.load_profile()
        build_volume = profile["build_volume_mm"]
        if settings.get("gcode_flavor") != "marlin":
            risks.append("gcode_flavor não está em Marlin para o fluxo Snapmaker.")
        if settings.get("printer_model") != "Snapmaker U1 0.4 nozzle":
            risks.append("printer_model exportado difere do perfil seguro esperado.")
        if settings.get("use_relative_e_distances") == "1":
            risks.append("Extrusão relativa ainda ativa no export final.")
        if settings.get("use_relative_e_distances") == "0":
            for key in ("before_layer_change_gcode", "layer_change_gcode", "layer_gcode"):
                current = settings.get(key)
                if isinstance(current, str) and "G92 E0" in current:
                    risks.append(f"{key} contém G92 E0 apesar do fluxo usar extrusão absoluta.")
        if settings.get("prime_tower_width") not in {None, "2"}:
            findings.append("prime_tower_width foi preservado com valor diferente do fallback mínimo.")
        if settings.get("raft_first_layer_expansion") not in {None, "0"}:
            risks.append("raft_first_layer_expansion não foi normalizado para valor compatível.")

        printable_area = settings.get("printable_area")
        expected_area = [
            "0x0",
            f"{int(build_volume['x'])}x0",
            f"{int(build_volume['x'])}x{int(build_volume['y'])}",
            f"0x{int(build_volume['y'])}",
        ]
        if printable_area is not None and printable_area != expected_area:
            risks.append("printable_area ainda diverge da mesa da Snapmaker U1.")
        bed_exclude_area = settings.get("bed_exclude_area")
        if bed_exclude_area is not None and bed_exclude_area != []:
            risks.append("bed_exclude_area ainda preserva zonas herdadas incompatíveis com a U1.")

        if root is not None:
            ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
            vertices = root.findall("m:resources/m:object/m:mesh/m:vertices/m:vertex", ns)
            if vertices:
                xs = [float(vertex.attrib["x"]) for vertex in vertices]
                ys = [float(vertex.attrib["y"]) for vertex in vertices]
                zs = [float(vertex.attrib["z"]) for vertex in vertices]
                if min(xs) < 0 or min(ys) < 0 or min(zs) < 0:
                    risks.append("Geometria final contém coordenadas negativas fora da mesa.")
                if max(xs) > float(build_volume["x"]) or max(ys) > float(build_volume["y"]) or max(zs) > float(build_volume["z"]):
                    risks.append("Geometria final excede o envelope útil da Snapmaker U1.")

        initial_speed = settings.get("initial_layer_speed", ["18"])
        findings.append(f"Velocidade inicial registrada: {initial_speed[0] if isinstance(initial_speed, list) else initial_speed} mm/s.")

        estimates = {
            "build_volume_mm": build_volume,
            "estimated_material_cost": None,
            "estimated_print_time_minutes": None,
            "estimated_filament_g": None,
        }
        return {
            "status": "ok" if not risks else "partial",
            "findings": findings,
            "risks": risks,
            "estimates": estimates,
        }
