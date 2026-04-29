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
            model_name = "3D/3dmodel.model" if "3D/3dmodel.model" in names else None

        profile = self.profile_service.load_profile()
        build_volume = profile["build_volume_mm"]
        if settings.get("gcode_flavor") != "marlin":
            risks.append("gcode_flavor não está em Marlin para o fluxo Snapmaker.")
        if settings.get("printer_model") != "Snapmaker U1 0.4 nozzle":
            risks.append("printer_model exportado difere do perfil seguro esperado.")

        # use_relative_e_distances=1 is REQUIRED for Prime/Wipe Tower in Snapmaker Orca.
        # If a wipe tower is configured and relative E is disabled, Orca will error on open.
        prime_tower_active = settings.get("prime_tower_enable") in {"1", "true", True} or (
            settings.get("prime_tower_width") not in {None, "", "0", "2"}
        )
        has_relative_e = settings.get("use_relative_e_distances") == "1"
        if prime_tower_active and not has_relative_e:
            risks.append(
                "Prime Tower / Wipe Tower está ativo mas use_relative_e_distances=0. "
                "O Snapmaker Orca vai rejeitar o projeto com erro. "
                "Ative 'Relative E distances' no perfil da impressora antes de exportar."
            )

        if not has_relative_e:
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

        if model_name is not None:
            bounds = self.extract_model_bounds_streaming(file_path, model_name)
            if bounds is None:
                risks.append("Não foi possível validar envelope geométrico do 3MF final em modo seguro.")
            else:
                min_x, min_y, min_z, max_x, max_y, max_z, vertex_count, truncated = bounds
                if vertex_count > 0:
                    if min_x < 0 or min_y < 0 or min_z < 0:
                        risks.append("Geometria final contém coordenadas negativas fora da mesa.")
                    if (
                        max_x > float(build_volume["x"])
                        or max_y > float(build_volume["y"])
                        or max_z > float(build_volume["z"])
                    ):
                        risks.append("Geometria final excede o envelope útil da Snapmaker U1.")
                    if truncated:
                        findings.append(
                            "Validação geométrica executada por amostragem de segurança (arquivo muito grande)."
                        )

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

    def extract_model_bounds_streaming(
        self,
        file_path: Path,
        model_name: str,
        *,
        max_vertices: int = 1_500_000,
    ) -> tuple[float, float, float, float, float, float, int, bool] | None:
        try:
            with zipfile.ZipFile(file_path) as archive:
                with archive.open(model_name, "r") as model_stream:
                    min_x = min_y = min_z = float("inf")
                    max_x = max_y = max_z = float("-inf")
                    vertex_count = 0
                    truncated = False

                    for _, elem in ET.iterparse(model_stream, events=("start",)):
                        if not elem.tag.endswith("vertex"):
                            continue
                        try:
                            x = float(elem.attrib.get("x", "0"))
                            y = float(elem.attrib.get("y", "0"))
                            z = float(elem.attrib.get("z", "0"))
                        except (TypeError, ValueError):
                            elem.clear()
                            continue
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        min_z = min(min_z, z)
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
                        max_z = max(max_z, z)
                        vertex_count += 1
                        if vertex_count >= max_vertices:
                            truncated = True
                            elem.clear()
                            break
                        elem.clear()

                    if vertex_count == 0:
                        return None
                    return (
                        min_x,
                        min_y,
                        min_z,
                        max_x,
                        max_y,
                        max_z,
                        vertex_count,
                        truncated,
                    )
        except Exception:
            return None
