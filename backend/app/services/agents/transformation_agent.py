from __future__ import annotations

from typing import Any

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import TRANSFORMATION_PROMPT
from app.services.transformation_service import TransformationService


class TransformationAgent(BaseAgent):
    name = "transformation_agent"
    prompt = TRANSFORMATION_PROMPT

    def __init__(self) -> None:
        self.transforms = TransformationService()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        request = context["request"]
        metrics = context.get("geometry_metrics", {})
        source_file = context["source_file"]
        plan = self._build_plan(context, metrics)

        if not plan["should_transform"]:
            return self.result(
                status="skipped",
                etapa="transformacoes_geometricas_controladas",
                achados=["Nenhuma transformação geométrica adicional foi necessária nesta execução."],
                riscos=[],
                perguntas_ao_usuario=[],
                acoes_executadas=["Plano de transformação analisado e descartado para este caso."],
                artefatos_gerados=[],
                caminho_de_saida=context["folders"]["processed"].as_posix(),
                extra={"decisions": plan["decisions"], "fallbacks": [], "limitations": []},
            )

        transformed = self.transforms.apply_transformations(source_file, context["folders"]["processed"], plan)
        if transformed["artifacts"]:
            context["working_file"] = transformed["artifacts"][-1]

        risks = []
        if any(decision.get("destructive") for decision in transformed["decisions"]):
            risks.append("Transformações destrutivas foram aplicadas; compare a versão original e a processada antes de produção crítica.")

        return self.result(
            status="ok",
            etapa="transformacoes_geometricas_controladas",
            achados=["Plano de transformação geométrica executado com versionamento."] if transformed["artifacts"] else [],
            riscos=risks,
            perguntas_ao_usuario=[],
            acoes_executadas=transformed["actions"],
            artefatos_gerados=transformed["artifacts"],
            caminho_de_saida=context["folders"]["processed"].as_posix(),
            extra={
                "decisions": plan["decisions"] + transformed["decisions"],
                "fallbacks": [],
                "limitations": [],
            },
        )

    def _build_plan(self, context: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
        request = context["request"]
        prefs = request.transform_preferences
        extents = metrics.get("extents_mm_assumed") or []
        decisions: list[dict[str, Any]] = []
        plan: dict[str, Any] = {
            "should_transform": False,
            "decisions": decisions,
        }

        if request.scale_mode == "fit_to_bed" and extents:
            limits = (270.0, 270.0, 270.0)
            factor = min(limit / extent for extent, limit in zip(extents, limits) if extent > 0)
            if factor < 1.0:
                plan["scale_factor"] = round(factor * 0.97, 5)
                plan["should_transform"] = True
                decisions.append(
                    {
                        "stage_key": "transformation",
                        "action": "scale_uniform",
                        "reason": "Peça excede o envelope útil e o usuário permitiu ajuste automático à mesa.",
                        "impact": "redução uniforme de escala",
                        "destructive": True,
                    }
                )

        if prefs.add_helper_base or metrics.get("adhesion_mode") == "raft":
            plan["add_helper_base"] = True
            plan["base_thickness_mm"] = 1.2
            plan["should_transform"] = True
            decisions.append(
                {
                    "stage_key": "transformation",
                    "action": "add_helper_base",
                    "reason": "Geometria com baixa área de contato inicial ou solicitação explícita do usuário.",
                    "impact": "adição de base auxiliar",
                    "destructive": False,
                }
            )

        if prefs.simplify_microdetails and metrics.get("tiny_feature_count", 0) > 0:
            plan["simplify_ratio"] = 0.75
            plan["should_transform"] = True
            decisions.append(
                {
                    "stage_key": "transformation",
                    "action": "simplify_microdetails",
                    "reason": "Há microdetalhes abaixo da capacidade provável do nozzle atual.",
                    "impact": "redução de detalhes pequenos",
                    "destructive": True,
                }
            )

        if request.hollowing or request.hollowing_preferences.enabled:
            plan["hollowing"] = True
            plan["shell_thickness_mm"] = request.hollowing_preferences.shell_thickness_mm
            plan["should_transform"] = True
            decisions.append(
                {
                    "stage_key": "transformation",
                    "action": "hollowing",
                    "reason": "Solicitação explícita de hollowing.",
                    "impact": "remoção de volume interno",
                    "destructive": True,
                }
            )

        return plan
