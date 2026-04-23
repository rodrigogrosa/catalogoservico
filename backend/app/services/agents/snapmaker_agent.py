from __future__ import annotations

from typing import Any

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import SNAPMAKER_PROMPT
from app.services.snapmaker_profile_service import SnapmakerProfileService


class SnapmakerAgent(BaseAgent):
    name = "snapmaker_agent"
    prompt = SNAPMAKER_PROMPT

    def __init__(self) -> None:
        self.profile_service = SnapmakerProfileService()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        profile = self.profile_service.load_profile()
        metrics = context.get("geometry_metrics", {})
        request = context["request"]
        extents = metrics.get("extents_mm_assumed") or []
        findings = [f"Perfil usado: {profile['machine_name']} / {profile['profile_id']}."]
        risks: list[str] = []
        questions: list[dict[str, Any]] = []
        actions = ["Validação de envelope e preset Snapmaker executados."]
        decisions: list[dict[str, Any]] = []

        build_volume = profile["build_volume_mm"]
        preset = self.profile_service.get_preset(request.objective_preset)
        findings.append(f"Preset aplicado: {request.objective_preset}.")
        decisions.append(
            {
                "stage_key": "snapmaker",
                "action": "select_objective_preset",
                "reason": "Preset objetivo escolhido para orientar velocidades e densidade base.",
                "impact": request.objective_preset,
                "destructive": False,
            }
        )

        support_required = bool(metrics.get("support_required"))
        support_area_ratio = metrics.get("support_area_ratio", 0.0)
        adhesion_mode = str(metrics.get("adhesion_mode", "skirt"))
        adhesion_risk = str(metrics.get("adhesion_risk", "unknown"))
        brim_width_mm = int(metrics.get("brim_width_mm", 0) or 0)
        raft_layers = int(metrics.get("raft_layers", 0) or 0)

        support_plan = {
            "enabled": False,
            "type": "tree(auto)",
            "threshold_angle": 25,
            "build_plate_only": False,
            "reason": "user_disabled",
        }
        adhesion_plan = {
            "mode": "skirt",
            "brim_width_mm": 0,
            "raft_layers": 0,
            "skirt_loops": 2,
            "initial_layer_speed_mm_s": profile["safe_defaults"]["initial_layer_speed_mm_s"],
            "initial_layer_infill_speed_mm_s": profile["safe_defaults"]["initial_layer_speed_mm_s"],
            "initial_layer_acceleration_mm_s2": profile["safe_defaults"]["initial_layer_acceleration_mm_s2"],
            "initial_layer_flow_ratio": 1.0,
            "initial_layer_height_mm": profile["safe_defaults"]["initial_layer_height_mm"],
            "reason": "default_low_risk",
        }

        if extents:
            limits = [build_volume["x"], build_volume["y"], build_volume["z"]]
            if any(extent > limit for extent, limit in zip(extents, limits)):
                if request.scale_mode == "fit_to_bed":
                    findings.append("Envelope excedido detectado; escala automática para caber na U1 foi autorizada.")
                    decisions.append(
                        {
                            "stage_key": "snapmaker",
                            "action": "auto_scale_to_fit",
                            "reason": "Bounding box excede a máquina, mas o usuário autorizou ajuste automático à mesa.",
                            "impact": "fit_to_bed",
                            "destructive": True,
                        }
                    )
                else:
                    risks.append("Modelo excede o volume configurado para a Snapmaker U1; divisão em partes ou redução será necessária.")
                    questions.append(
                        {
                            "code": "split_or_scale",
                            "question": "Deseja priorizar redução de escala ou divisão multipartes para caber na impressora?",
                            "reason": "O envelope atual excede o volume útil da Snapmaker U1.",
                            "severity": "high",
                            "kind": "blocking",
                        }
                    )
                    decisions.append(
                        {
                            "stage_key": "snapmaker",
                            "action": "flag_split_or_scale",
                            "reason": "Bounding box final excede o envelope útil da máquina.",
                            "impact": "bloqueio de entrega automática",
                            "destructive": False,
                        }
                    )
            if min(extents) < max(request.target_nozzle_mm * 2.0, 0.8):
                risks.append("Algumas espessuras aparentam ser muito finas para FDM robusto com o nozzle atual.")

        material_name = (request.target_material or "").upper() if request.target_material else None
        if material_name:
            material_rule = self.profile_service.get_material_rule(material_name)
            if material_rule:
                if request.target_nozzle_mm < material_rule["minimum_nozzle_mm"]:
                    risks.append(
                        f"{material_name} pede nozzle mínimo de {material_rule['minimum_nozzle_mm']} mm no perfil seguro atual."
                    )
                if material_rule["abrasive"]:
                    risks.append(f"{material_name} é abrasivo e deve usar nozzle endurecido.")
                decisions.append(
                    {
                        "stage_key": "snapmaker",
                        "action": "validate_material_nozzle",
                        "reason": "Compatibilidade material/nozzle verificada contra perfil central da U1.",
                        "impact": material_name,
                        "destructive": False,
                    }
                )

        if request.supports == "disabled":
            if support_required:
                risks.append("A geometria indica overhangs sem apoio, mas os suportes foram explicitamente desabilitados.")
            actions.append("Suportes mantidos desabilitados por solicitação explícita.")
        else:
            if support_required:
                support_plan = {
                    "enabled": True,
                    "type": "tree(auto)",
                    "threshold_angle": 25,
                    "build_plate_only": True,
                    "reason": "critical_overhangs_detected",
                }
                findings.append(f"Overhangs críticos detectados (área relativa {support_area_ratio:.2%}); suportes automáticos serão inseridos.")
                actions.append("Suportes automáticos ativados por análise de overhang.")
                decisions.append(
                    {
                        "stage_key": "snapmaker",
                        "action": "enable_supports",
                        "reason": "Overhangs sem apoio detectados na malha.",
                        "impact": "tree(auto) build_plate_only",
                        "destructive": False,
                    }
                )
            elif request.supports == "ask":
                questions.append(
                    {
                        "code": "support_strategy",
                        "question": "Deseja priorizar menos marcas superficiais ou maior segurança de impressão para os suportes?",
                        "reason": "A geometria não exige suporte crítico, mas a estratégia ainda afeta acabamento e taxa de sucesso.",
                        "severity": "medium",
                        "kind": "recommended",
                    }
                )

        if adhesion_mode == "raft":
            adhesion_plan = {
                "mode": "raft",
                "brim_width_mm": 0,
                "raft_layers": max(2, raft_layers),
                "skirt_loops": 1,
                "initial_layer_speed_mm_s": 16,
                "initial_layer_infill_speed_mm_s": 16,
                "initial_layer_acceleration_mm_s2": 220,
                "initial_layer_flow_ratio": 1.05,
                "initial_layer_height_mm": 0.22,
                "reason": "minimal_contact_area",
            }
            findings.append("Primeira camada configurada com raft por área de contato muito pequena.")
            decisions.append(
                {
                    "stage_key": "snapmaker",
                    "action": "select_adhesion_strategy",
                    "reason": "Área de contato inicial crítica.",
                    "impact": "raft",
                    "destructive": False,
                }
            )
        elif adhesion_mode == "brim":
            adhesion_plan = {
                "mode": "brim",
                "brim_width_mm": max(4, brim_width_mm),
                "raft_layers": 0,
                "skirt_loops": 2,
                "initial_layer_speed_mm_s": 18 if adhesion_risk == "medium" else 22,
                "initial_layer_infill_speed_mm_s": 18 if adhesion_risk == "medium" else 22,
                "initial_layer_acceleration_mm_s2": 280 if adhesion_risk == "medium" else 360,
                "initial_layer_flow_ratio": 1.04 if adhesion_risk == "medium" else 1.02,
                "initial_layer_height_mm": profile["safe_defaults"]["initial_layer_height_mm"],
                "reason": "reduced_contact_or_tall_geometry",
            }
            findings.append(f"Primeira camada reforçada com brim de {adhesion_plan['brim_width_mm']} mm.")
            decisions.append(
                {
                    "stage_key": "snapmaker",
                    "action": "select_adhesion_strategy",
                    "reason": "Contato moderado ou geometria esbelta.",
                    "impact": "brim",
                    "destructive": False,
                }
            )
        else:
            findings.append("Primeira camada mantida com skirt e velocidades conservadoras.")

        context["support_plan"] = support_plan
        context["adhesion_plan"] = adhesion_plan
        context["snapmaker_preset"] = preset

        return self.result(
            status="ok",
            etapa="adaptacao_para_snapmaker_u1",
            achados=findings,
            riscos=risks,
            perguntas_ao_usuario=questions,
            acoes_executadas=actions,
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["processed"].as_posix(),
            extra={
                "support_plan": support_plan,
                "adhesion_plan": adhesion_plan,
                "preset": preset,
                "decisions": decisions,
                "limitations": [],
                "fallbacks": [],
            },
        )
