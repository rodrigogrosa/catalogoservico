from __future__ import annotations

from pathlib import Path
from typing import Any
import shutil
import zipfile
from xml.etree import ElementTree as ET

from app.services.storage_service import StorageService


class MeshAnalysisService:
    ORIENTATION_CANDIDATES = (
        ("identity", None),
        ("rotate_x_90", ("x", 90)),
        ("rotate_x_180", ("x", 180)),
        ("rotate_y_90", ("y", 90)),
        ("rotate_y_180", ("y", 180)),
        ("rotate_z_90", ("z", 90)),
    )

    def __init__(self) -> None:
        self.storage = StorageService()

    def analyze(self, file_path: Path) -> dict[str, Any]:
        extension = file_path.suffix.lower().lstrip(".")
        if extension == "slt":
            extension = "stl"
        fallback = {
            "status": "partial",
            "can_repair": False,
            "findings": [f"Análise geométrica detalhada indisponível para .{extension} sem adaptador especializado."],
            "risks": [],
            "metrics": {},
            "questions": [],
        }

        if extension == "3mf" and zipfile.is_zipfile(file_path):
            return self._analyze_3mf_archive(file_path)

        if extension not in {"stl", "obj", "ply", "off", "3mf"}:
            if extension in {"step", "stp", "amf"}:
                fallback["questions"] = [
                    {
                        "code": "cad_conversion_adapter",
                        "question": "Deseja preservar a semântica CAD original ou priorizar uma tesselação para impressão?",
                        "reason": "Conversão CAD -> malha pode introduzir perda de intenção geométrica.",
                        "severity": "high",
                        "kind": "blocking",
                    }
                ]
            return fallback

        try:
            import trimesh
        except ImportError:
            fallback["findings"].append("Dependência trimesh ausente; executando apenas inspeção superficial.")
            return fallback

        try:
            mesh = trimesh.load(file_path, force="mesh")
            if mesh.is_empty:
                return {
                    "status": "failed",
                    "can_repair": False,
                    "findings": ["Malha vazia ou ilegível."],
                    "risks": ["Arquivo não pode ser preparado para impressão sem geometria válida."],
                    "metrics": {},
                    "questions": [],
                }

            bounds = mesh.bounds.tolist() if mesh.bounds is not None else []
            extents = mesh.extents.tolist() if mesh.extents is not None else []
            findings: list[str] = []
            risks: list[str] = []
            questions: list[dict[str, Any]] = []

            if not mesh.is_watertight:
                findings.append("Malha não watertight; pode haver vazamentos, buracos ou superfícies abertas.")
            if mesh.body_count > 1:
                findings.append(f"Modelo possui {mesh.body_count} corpos desconectados.")
            if hasattr(mesh, "is_winding_consistent") and not mesh.is_winding_consistent:
                findings.append("Normais ou winding inconsistentes detectados.")

            unit_metrics = self._infer_units(mesh)
            if unit_metrics["unit_warning"]:
                risks.append(unit_metrics["unit_warning"])
                questions.append(
                    {
                        "code": "unit_scale_confirmation",
                        "question": "Deseja manter a unidade original detectada ou normalizar explicitamente para milímetros?",
                        "reason": unit_metrics["unit_warning"],
                        "severity": "high",
                        "kind": "blocking",
                    }
                )

            overhang_metrics = self._estimate_support_need(mesh)
            adhesion_metrics = self._estimate_first_layer_adhesion(mesh, overhang_metrics)
            thin_wall_metrics = self._estimate_thin_walls(mesh)
            tiny_feature_metrics = self._estimate_microdetails(mesh)
            cavity_metrics = self._estimate_closed_cavities(mesh)
            bridge_metrics = self._estimate_bridges(mesh)
            fit_metrics = self._estimate_fit_risks(mesh, file_path)
            orientation_metrics = self._suggest_orientation(mesh, objective="support_economy")

            if overhang_metrics["support_required"]:
                findings.append("Overhangs sem apoio detectados; suportes automáticos são recomendados.")
            elif overhang_metrics["risky_face_count"] > 0:
                findings.append("Há overhangs leves; suporte pode melhorar confiabilidade dependendo da prioridade.")

            if adhesion_metrics["adhesion_risk"] != "low":
                findings.append(
                    f"Fixação de primeira camada requer estratégia conservadora ({adhesion_metrics['adhesion_mode']})."
                )

            if thin_wall_metrics["thin_wall_edge_count"] > 0:
                findings.append(
                    f"Foram detectadas {thin_wall_metrics['thin_wall_edge_count']} arestas/regiões potencialmente finas para nozzle 0.4."
                )
            if tiny_feature_metrics["tiny_feature_count"] > 0:
                findings.append(
                    f"Existem {tiny_feature_metrics['tiny_feature_count']} detalhes abaixo da capacidade provável do nozzle atual."
                )
            if cavity_metrics["closed_cavity_count"] > 0:
                risks.append("Foram detectadas cavidades internas fechadas que podem dificultar hollowing ou suportes internos.")
            if bridge_metrics["bridge_face_count"] > 0:
                findings.append(f"Regiões de ponte detectadas: {bridge_metrics['bridge_face_count']} faces candidatas.")
            if fit_metrics["fit_risk"]:
                risks.append(fit_metrics["fit_risk"])

            if extents and max(extents) > 500:
                risks.append("Modelo excede envelopes comuns de impressoras FDM; provavelmente exigirá divisão ou redução.")

            findings.append(
                f"Orientação sugerida: {orientation_metrics['recommended_orientation']} (suporte relativo {orientation_metrics['support_area_ratio']:.2%})."
            )

            return {
                "status": "ok",
                "can_repair": True,
                "findings": findings or ["Nenhuma falha crítica detectada na malha base."],
                "risks": risks,
                "metrics": {
                    "faces": int(len(mesh.faces)),
                    "vertices": int(len(mesh.vertices)),
                    "body_count": int(mesh.body_count),
                    "is_watertight": bool(mesh.is_watertight),
                    "is_volume": bool(mesh.is_volume),
                    "extents_mm_assumed": [round(value, 3) for value in extents],
                    "bounds_mm_assumed": bounds,
                    "volume_mm3_assumed": round(float(mesh.volume), 3) if mesh.is_volume else None,
                    **unit_metrics,
                    **overhang_metrics,
                    **adhesion_metrics,
                    **thin_wall_metrics,
                    **tiny_feature_metrics,
                    **cavity_metrics,
                    **bridge_metrics,
                    **fit_metrics,
                    **orientation_metrics,
                },
                "questions": questions,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "can_repair": False,
                "findings": [f"Falha ao interpretar malha: {exc}"],
                "risks": ["Análise inconclusiva; a exportação final deve ser tratada como não confiável até nova inspeção."],
                "metrics": {},
                "questions": [],
            }

    def repair(self, file_path: Path, output_dir: Path) -> dict[str, Any]:
        extension = file_path.suffix.lower().lstrip(".")
        if extension == "slt":
            extension = "stl"
        if extension == "3mf" and zipfile.is_zipfile(file_path):
            return {
                "status": "partial",
                "output_file": "",
                "actions": [
                    "Reparo automático de malha para 3MF compactado não foi executado.",
                    "Use o artefato exportado compatível com Snapmaker em vez de uma cópia bruta do container.",
                ],
            }
        if extension not in {"stl", "obj", "ply", "off"}:
            destination = self.storage.next_generated_file(output_dir, f"{file_path.stem}_repaired", file_path.suffix)
            shutil.copy2(file_path, destination)
            return {
                "status": "partial",
                "output_file": str(destination),
                "actions": ["Reparo automático indisponível para este formato; arquivo foi apenas versionado para processamento."],
            }

        try:
            import trimesh
        except ImportError:
            destination = self.storage.next_generated_file(output_dir, f"{file_path.stem}_repaired", file_path.suffix)
            shutil.copy2(file_path, destination)
            return {
                "status": "partial",
                "output_file": str(destination),
                "actions": ["trimesh não instalado; reparo automático pulado."],
            }

        mesh = trimesh.load(file_path, force="mesh")
        actions: list[str] = []
        trimesh.repair.fix_normals(mesh)
        actions.append("Normais recalculadas.")
        try:
            trimesh.repair.fill_holes(mesh)
            actions.append("Preenchimento de buracos simples executado.")
        except Exception:
            actions.append("Preenchimento de buracos simples não foi aplicável.")

        destination = self.storage.next_generated_file(output_dir, f"{file_path.stem}_repaired", file_path.suffix)
        mesh.export(destination)
        return {
            "status": "ok",
            "output_file": str(destination),
            "actions": actions,
        }

    def _analyze_3mf_archive(self, file_path: Path) -> dict[str, Any]:
        findings: list[str] = []
        risks: list[str] = []
        questions: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}

        try:
            with zipfile.ZipFile(file_path) as archive:
                names = archive.namelist()
                metrics["archive_entries"] = len(names)
                metrics["plate_preview_count"] = len([name for name in names if name.lower().startswith("metadata/plate_") and name.lower().endswith(".png")])
                metrics["has_project_settings"] = "Metadata/project_settings.config" in names
                metrics["has_model_settings"] = "Metadata/model_settings.config" in names

                root = ET.fromstring(archive.read("3D/3dmodel.model"))
                ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
                resources = root.find("m:resources", ns)
                build = root.find("m:build", ns)
                objects = resources.findall("m:object", ns) if resources is not None else []
                items = build.findall("m:item", ns) if build is not None else []
                metrics["resource_object_count"] = len(objects)
                metrics["build_item_count"] = len(items)

                if "Metadata/model_settings.config" in names:
                    model_settings = ET.fromstring(archive.read("Metadata/model_settings.config"))
                    plates = model_settings.findall("plate")
                    metrics["plate_count"] = len(plates)
                    findings.append(f"Projeto 3MF com {len(plates)} plate(s) detectados.")
                else:
                    metrics["plate_count"] = 1 if items else 0
                    findings.append("Projeto 3MF sem model_settings.config; compatibilidade de layout pode ser parcial.")

                if items:
                    findings.append(f"Build com {len(items)} item(ns) detectados.")
                if len(names) > 200:
                    risks.append("Pacote 3MF complexo; a validação geométrica foi executada em modo leve para evitar travamento.")
                if metrics["plate_count"] > 1:
                    findings.append("Estrutura multi-plate detectada e elegível para preservação na conversão.")

                # Heurística conservadora: arquivos grandes e 3MF compostos pedem análise completa apenas no slicer.
                risks.append("Análise geométrica de 3MF foi executada em modo leve; valide detalhes finos no preview e no slicer final.")
                return {
                    "status": "ok",
                    "can_repair": False,
                    "findings": findings or ["Projeto 3MF inspecionado em modo leve."],
                    "risks": risks,
                    "metrics": metrics,
                    "questions": questions,
                }
        except Exception as exc:
            return {
                "status": "failed",
                "can_repair": False,
                "findings": [f"Falha ao inspecionar pacote 3MF: {exc}"],
                "risks": ["Análise geométrica de 3MF inconclusiva; trate a saída como não confiável até nova inspeção."],
                "metrics": metrics,
                "questions": questions,
            }

    def _infer_units(self, mesh: Any) -> dict[str, Any]:
        extents = mesh.extents.tolist() if mesh.extents is not None else []
        if not extents:
            return {
                "unit_inference": "unknown",
                "unit_scale_factor_to_mm": 1.0,
                "unit_warning": None,
            }
        max_extent = max(extents)
        if max_extent < 1.0:
            return {
                "unit_inference": "meters_or_inches",
                "unit_scale_factor_to_mm": 1000.0,
                "unit_warning": "Escala extremamente pequena; o modelo pode estar em metros ou polegadas e precisa de confirmação.",
            }
        if max_extent <= 20.0:
            return {
                "unit_inference": "inches_likely",
                "unit_scale_factor_to_mm": 25.4,
                "unit_warning": "Dimensões compatíveis com polegadas; a unidade deve ser confirmada antes da exportação final.",
            }
        return {
            "unit_inference": "millimeters_likely",
            "unit_scale_factor_to_mm": 1.0,
            "unit_warning": None,
        }

    def _estimate_support_need(self, mesh: Any) -> dict[str, Any]:
        try:
            import numpy as np
        except ImportError:
            return {
                "support_required": False,
                "support_reason": "numpy_indisponivel",
                "support_area_ratio": 0.0,
                "risky_face_count": 0,
            }

        if len(mesh.faces) == 0:
            return {
                "support_required": False,
                "support_reason": "malha_sem_faces",
                "support_area_ratio": 0.0,
                "risky_face_count": 0,
            }

        normals = np.asarray(mesh.face_normals)
        areas = np.asarray(mesh.area_faces)
        centers = np.asarray(mesh.triangles_center)
        z_min = float(mesh.bounds[0][2]) if mesh.bounds is not None else 0.0
        risky_faces = (normals[:, 2] < -0.35) & (centers[:, 2] > z_min + 1.0)
        risky_face_count = int(risky_faces.sum())
        risky_area = float(areas[risky_faces].sum()) if risky_face_count else 0.0
        total_area = float(areas.sum()) if len(areas) else 0.0
        support_area_ratio = round((risky_area / total_area), 4) if total_area > 0 else 0.0
        support_required = risky_face_count >= 25 or support_area_ratio >= 0.015

        return {
            "support_required": support_required,
            "support_reason": "downward_faces_detected" if support_required else "no_critical_overhang_detected",
            "support_area_ratio": support_area_ratio,
            "risky_face_count": risky_face_count,
        }

    def _estimate_first_layer_adhesion(self, mesh: Any, overhang_metrics: dict[str, Any]) -> dict[str, Any]:
        try:
            import numpy as np
        except ImportError:
            return {
                "contact_area_mm2": 0.0,
                "footprint_bbox_area_mm2": 0.0,
                "contact_ratio": 0.0,
                "slenderness_ratio": 0.0,
                "adhesion_risk": "unknown",
                "adhesion_mode": "skirt",
                "adhesion_reason": "numpy_indisponivel",
                "brim_width_mm": 0,
                "raft_layers": 0,
            }

        if len(mesh.faces) == 0 or mesh.bounds is None:
            return {
                "contact_area_mm2": 0.0,
                "footprint_bbox_area_mm2": 0.0,
                "contact_ratio": 0.0,
                "slenderness_ratio": 0.0,
                "adhesion_risk": "unknown",
                "adhesion_mode": "skirt",
                "adhesion_reason": "malha_sem_faces",
                "brim_width_mm": 0,
                "raft_layers": 0,
            }

        normals = np.asarray(mesh.face_normals)
        areas = np.asarray(mesh.area_faces)
        centers = np.asarray(mesh.triangles_center)
        extents = np.asarray(mesh.extents)
        z_min = float(mesh.bounds[0][2])
        bbox_area = float(extents[0] * extents[1]) if len(extents) >= 2 else 0.0

        bottom_faces = (normals[:, 2] < -0.92) & (centers[:, 2] <= z_min + 0.3)
        contact_area = float(areas[bottom_faces].sum()) if int(bottom_faces.sum()) else 0.0
        contact_ratio = round((contact_area / bbox_area), 4) if bbox_area > 0 else 0.0
        height = float(extents[2]) if len(extents) >= 3 else 0.0
        base_min = float(min(extents[0], extents[1])) if len(extents) >= 2 else 0.0
        slenderness_ratio = round((height / base_min), 4) if base_min > 0 else 0.0
        support_heavy = bool(overhang_metrics.get("support_required")) and float(overhang_metrics.get("support_area_ratio", 0.0)) >= 0.03

        adhesion_risk = "low"
        adhesion_mode = "skirt"
        adhesion_reason = "stable_footprint"
        brim_width = 0
        raft_layers = 0

        if bbox_area <= 0 or contact_area < 60 or (contact_ratio < 0.05 and height > 25):
            adhesion_risk = "high"
            adhesion_mode = "raft"
            adhesion_reason = "minimal_contact_area"
            raft_layers = 2
        elif contact_area < 300 or contact_ratio < 0.16 or slenderness_ratio >= 2.4 or support_heavy:
            adhesion_risk = "medium"
            adhesion_mode = "brim"
            adhesion_reason = "reduced_contact_or_tall_geometry"
            brim_width = 8 if support_heavy or slenderness_ratio >= 3.2 else 6
        elif contact_area < 900 or slenderness_ratio >= 1.6:
            adhesion_mode = "brim"
            adhesion_reason = "moderate_contact_area"
            brim_width = 4

        return {
            "contact_area_mm2": round(contact_area, 3),
            "footprint_bbox_area_mm2": round(bbox_area, 3),
            "contact_ratio": contact_ratio,
            "slenderness_ratio": slenderness_ratio,
            "adhesion_risk": adhesion_risk,
            "adhesion_mode": adhesion_mode,
            "adhesion_reason": adhesion_reason,
            "brim_width_mm": brim_width,
            "raft_layers": raft_layers,
        }

    def _estimate_thin_walls(self, mesh: Any) -> dict[str, Any]:
        try:
            import numpy as np
        except ImportError:
            return {"thin_wall_edge_count": 0, "thin_wall_ratio": 0.0, "recommended_min_wall_mm": 0.85}

        edges = np.asarray(mesh.edges_unique_length)
        if len(edges) == 0:
            return {"thin_wall_edge_count": 0, "thin_wall_ratio": 0.0, "recommended_min_wall_mm": 0.85}
        threshold = 0.85
        count = int((edges < threshold).sum())
        ratio = round(count / len(edges), 4)
        return {
            "thin_wall_edge_count": count,
            "thin_wall_ratio": ratio,
            "recommended_min_wall_mm": threshold,
        }

    def _estimate_microdetails(self, mesh: Any) -> dict[str, Any]:
        try:
            import numpy as np
        except ImportError:
            return {"tiny_feature_count": 0, "min_feature_threshold_mm": 0.4}

        edges = np.asarray(mesh.edges_unique_length)
        if len(edges) == 0:
            return {"tiny_feature_count": 0, "min_feature_threshold_mm": 0.4}
        threshold = 0.35
        tiny_count = int((edges < threshold).sum())
        return {
            "tiny_feature_count": tiny_count,
            "min_feature_threshold_mm": threshold,
        }

    def _estimate_closed_cavities(self, mesh: Any) -> dict[str, Any]:
        closed_cavity_count = 0
        try:
            split_meshes = mesh.split(only_watertight=False)
            if len(split_meshes) > 1:
                bounds = [candidate.bounds for candidate in split_meshes if candidate.bounds is not None]
                for index, outer in enumerate(bounds):
                    for inner_index, inner in enumerate(bounds):
                        if index == inner_index:
                            continue
                        if all(float(outer[0][axis]) <= float(inner[0][axis]) and float(outer[1][axis]) >= float(inner[1][axis]) for axis in range(3)):
                            closed_cavity_count += 1
        except Exception:
            closed_cavity_count = 0

        return {
            "closed_cavity_count": closed_cavity_count,
        }

    def _estimate_bridges(self, mesh: Any) -> dict[str, Any]:
        try:
            import numpy as np
        except ImportError:
            return {"bridge_face_count": 0, "bridge_risk": "unknown"}

        normals = np.asarray(mesh.face_normals)
        centers = np.asarray(mesh.triangles_center)
        z_min = float(mesh.bounds[0][2]) if mesh.bounds is not None else 0.0
        bridge_faces = (np.abs(normals[:, 2]) < 0.18) & (centers[:, 2] > z_min + 1.0)
        count = int(bridge_faces.sum())
        return {
            "bridge_face_count": count,
            "bridge_risk": "medium" if count > 0 else "low",
        }

    def _estimate_fit_risks(self, mesh: Any, file_path: Path) -> dict[str, Any]:
        source_name = file_path.stem.lower()
        fit_keywords = ("snap", "clip", "fit", "mount", "holder", "dock", "adapter", "rail", "axle")
        extents = mesh.extents.tolist() if mesh.extents is not None else []
        fit_risk = None
        if any(keyword in source_name for keyword in fit_keywords) and extents and min(extents) < 2.0:
            fit_risk = "Peça com provável função de encaixe tem detalhes muito pequenos; folgas/tolerâncias podem falhar na impressão."
        return {
            "fit_feature_detected": bool(fit_risk),
            "fit_risk": fit_risk,
        }

    def _suggest_orientation(self, mesh: Any, objective: str) -> dict[str, Any]:
        try:
            import trimesh
        except ImportError:
            return {
                "recommended_orientation": "identity",
                "orientation_reason": "trimesh_indisponivel",
                "orientation_priority": objective,
                "support_area_ratio": 0.0,
            }

        best: dict[str, Any] | None = None
        for label, transform in self.ORIENTATION_CANDIDATES:
            candidate = mesh.copy()
            if transform:
                axis, degrees = transform
                radians = degrees * 3.141592653589793 / 180.0
                if axis == "x":
                    matrix = trimesh.transformations.rotation_matrix(radians, [1, 0, 0])
                elif axis == "y":
                    matrix = trimesh.transformations.rotation_matrix(radians, [0, 1, 0])
                else:
                    matrix = trimesh.transformations.rotation_matrix(radians, [0, 0, 1])
                candidate.apply_transform(matrix)
            support = self._estimate_support_need(candidate)
            adhesion = self._estimate_first_layer_adhesion(candidate, support)
            score = self._score_orientation(support, adhesion, objective)
            proposal = {
                "recommended_orientation": label,
                "orientation_reason": f"support={support['support_area_ratio']:.2%}, adhesion={adhesion['adhesion_mode']}",
                "orientation_priority": objective,
                "support_area_ratio": support["support_area_ratio"],
                "orientation_contact_ratio": adhesion["contact_ratio"],
                "orientation_score": round(score, 4),
            }
            if best is None or proposal["orientation_score"] > best["orientation_score"]:
                best = proposal
        return best or {
            "recommended_orientation": "identity",
            "orientation_reason": "fallback_identity",
            "orientation_priority": objective,
            "support_area_ratio": 0.0,
        }

    def _score_orientation(self, support: dict[str, Any], adhesion: dict[str, Any], objective: str) -> float:
        support_penalty = float(support.get("support_area_ratio", 0.0))
        contact_bonus = float(adhesion.get("contact_ratio", 0.0))
        slenderness_penalty = 0.1 if adhesion.get("adhesion_mode") == "raft" else 0.0
        if objective == "aesthetics":
            return (contact_bonus * 0.4) - (support_penalty * 0.8) - slenderness_penalty
        if objective == "strength":
            return (contact_bonus * 0.5) - (support_penalty * 0.6) - slenderness_penalty
        if objective == "speed":
            return (contact_bonus * 0.25) - (support_penalty * 0.9)
        return (contact_bonus * 0.6) - (support_penalty * 1.0) - slenderness_penalty
