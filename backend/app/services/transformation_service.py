from __future__ import annotations

from pathlib import Path
from typing import Any

import trimesh

from app.services.storage_service import StorageService


class TransformationService:
    def __init__(self) -> None:
        self.storage = StorageService()

    def apply_transformations(
        self,
        file_path: Path,
        output_dir: Path,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        extension = file_path.suffix.lower().lstrip(".")
        if extension not in {"stl", "obj", "ply", "off"}:
            return {
                "status": "skipped",
                "actions": ["Transformações geométricas destrutivas não foram executadas para este formato."],
                "artifacts": [],
                "decisions": [],
            }

        mesh = trimesh.load(file_path, force="mesh")
        actions: list[str] = []
        decisions: list[dict[str, Any]] = []
        artifacts: list[str] = []
        working = mesh.copy()

        if plan.get("scale_factor") and plan.get("scale_factor") != 1.0:
            factor = float(plan["scale_factor"])
            working.apply_scale(factor)
            actions.append(f"Escala uniforme aplicada com fator {factor:.4f}.")
            decisions.append({"action": "scale_uniform", "factor": factor, "destructive": False})

        if plan.get("add_helper_base"):
            base_thickness = float(plan.get("base_thickness_mm", 1.2))
            base = self._make_helper_base(working, base_thickness)
            working = trimesh.util.concatenate([working, base])
            actions.append(f"Base auxiliar de {base_thickness:.2f} mm adicionada.")
            decisions.append({"action": "add_helper_base", "base_thickness_mm": base_thickness, "destructive": False})

        if plan.get("simplify_ratio"):
            ratio = float(plan["simplify_ratio"])
            target_faces = max(100, int(len(working.faces) * ratio))
            try:
                simplified = working.simplify_quadric_decimation(target_faces)
                if simplified is not None and len(simplified.faces) < len(working.faces):
                    working = simplified
                    actions.append(f"Simplificação aplicada para {len(working.faces)} faces.")
                    decisions.append({"action": "simplify", "target_faces": target_faces, "destructive": True})
            except Exception:
                actions.append("Simplificação solicitada, mas o backend atual não conseguiu executar a decimação.")

        if plan.get("hollowing"):
            hollow_result = self._try_hollowing(working, float(plan.get("shell_thickness_mm", 2.0)))
            actions.extend(hollow_result["actions"])
            decisions.extend(hollow_result["decisions"])
            if hollow_result.get("mesh") is not None:
                working = hollow_result["mesh"]

        destination = self.storage.next_generated_file(output_dir, f"{file_path.stem}_transformed", file_path.suffix)
        working.export(destination)
        artifacts.append(str(destination))
        return {
            "status": "ok",
            "actions": actions or ["Nenhuma transformação geométrica adicional foi necessária."],
            "artifacts": artifacts,
            "decisions": decisions,
        }

    def _make_helper_base(self, mesh: trimesh.Trimesh, thickness_mm: float) -> trimesh.Trimesh:
        bounds = mesh.bounds
        extents = mesh.extents
        transform = trimesh.transformations.translation_matrix(
            [
                float(bounds[0][0] + extents[0] / 2.0),
                float(bounds[0][1] + extents[1] / 2.0),
                float(bounds[0][2] - thickness_mm / 2.0),
            ]
        )
        base = trimesh.creation.box(extents=[max(extents[0] + 4.0, 4.0), max(extents[1] + 4.0, 4.0), thickness_mm])
        base.apply_transform(transform)
        return base

    def _try_hollowing(self, mesh: trimesh.Trimesh, shell_thickness_mm: float) -> dict[str, Any]:
        actions: list[str] = []
        decisions: list[dict[str, Any]] = []
        if not mesh.is_watertight:
            actions.append("Hollowing foi bloqueado porque a malha não está watertight.")
            decisions.append({"action": "hollowing_blocked", "reason": "mesh_not_watertight", "destructive": False})
            return {"mesh": None, "actions": actions, "decisions": decisions}

        centroid = mesh.centroid
        extents = mesh.extents
        min_extent = max(min(float(extents[0]), float(extents[1]), float(extents[2])), 0.001)
        if shell_thickness_mm * 2 >= min_extent:
            actions.append("Hollowing foi bloqueado porque a casca solicitada é grande demais para o volume.")
            decisions.append({"action": "hollowing_blocked", "reason": "shell_too_thick", "destructive": False})
            return {"mesh": None, "actions": actions, "decisions": decisions}

        # Fallback real e conservador: gera shell aproximada por contração uniforme do volume.
        # Não substitui boolean robusto, mas produz uma versão auditável quando a geometria permite.
        factor = max(0.1, 1.0 - ((shell_thickness_mm * 2.0) / min_extent))
        inner = mesh.copy()
        inner.vertices = centroid + (inner.vertices - centroid) * factor
        inner.invert()
        shell = trimesh.util.concatenate([mesh, inner])

        drain_hole = trimesh.creation.cylinder(radius=max(shell_thickness_mm * 0.9, 1.2), height=max(float(extents[2]) * 1.5, 6.0), sections=24)
        drain_hole.apply_translation(
            [
                float(bounds := mesh.bounds)[1][0] - max(shell_thickness_mm * 1.5, 2.0),
                float(bounds[0][1] + max(shell_thickness_mm * 1.5, 2.0)),
                float(bounds[0][2] + max(shell_thickness_mm, 1.0)),
            ]
        )
        shell = trimesh.util.concatenate([shell, drain_hole])
        actions.append(
            f"Hollowing aproximado aplicado com casca de {shell_thickness_mm:.2f} mm e furo de escape auxiliar."
        )
        decisions.append(
            {
                "action": "hollowing_approx_shell",
                "shell_thickness_mm": shell_thickness_mm,
                "destructive": True,
                "fallback": "uniform_shrink_shell",
            }
        )
        return {"mesh": shell, "actions": actions, "decisions": decisions}
