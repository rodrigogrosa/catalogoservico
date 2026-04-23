from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from app.core.config import get_settings
from app.services.agents.base import BaseAgent
from app.services.agents.prompts import GEOMETRY_PROMPT
from app.services.mesh_analysis_service import MeshAnalysisService


class GeometryAgent(BaseAgent):
    name = "geometry_agent"
    prompt = GEOMETRY_PROMPT

    def __init__(self) -> None:
        self.mesh_service = MeshAnalysisService()
        self.settings = get_settings()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        source_file = context["source_file"]
        analysis = self._run_with_timeout(self.mesh_service.analyze, source_file)
        actions = ["Análise geométrica executada."]
        artifacts: list[str] = []
        metrics = analysis.get("metrics", {})
        decisions: list[dict[str, Any]] = []
        limitations: list[str] = []

        if metrics.get("recommended_orientation"):
            decisions.append(
                {
                    "stage_key": "geometry",
                    "action": "suggest_orientation",
                    "reason": metrics.get("orientation_reason", "Heurística multiobjetivo aplicada."),
                    "impact": metrics.get("recommended_orientation"),
                    "destructive": False,
                }
            )
            context["orientation_plan"] = {
                "recommended_orientation": metrics["recommended_orientation"],
                "priority": metrics.get("orientation_priority", "support_economy"),
            }

        if metrics.get("thin_wall_edge_count", 0) > 0:
            decisions.append(
                {
                    "stage_key": "geometry",
                    "action": "flag_thin_walls",
                    "reason": "Foram encontradas regiões abaixo da espessura mínima recomendada.",
                    "impact": f"{metrics['thin_wall_edge_count']} regiões suspeitas",
                    "destructive": False,
                }
            )
        if metrics.get("tiny_feature_count", 0) > 0:
            decisions.append(
                {
                    "stage_key": "geometry",
                    "action": "flag_microdetails",
                    "reason": "Existem detalhes abaixo da capacidade provável do nozzle atual.",
                    "impact": f"{metrics['tiny_feature_count']} microdetalhes",
                    "destructive": False,
                }
            )
        if metrics.get("closed_cavity_count", 0) > 0:
            limitations.append("A análise de cavidades internas é heurística e deve ser confirmada em hollowing crítico.")

        if context["request"].repair_mesh:
            repair = self._run_with_timeout(self.mesh_service.repair, source_file, context["folders"]["processed"])
            actions.extend(repair["actions"])
            if repair["output_file"]:
                artifacts.append(repair["output_file"])
                context["working_file"] = repair["output_file"]

        return self.result(
            status="ok" if analysis["status"] != "failed" else "failed",
            etapa="analise_e_reparo_de_malha",
            achados=analysis["findings"],
            riscos=analysis["risks"],
            perguntas_ao_usuario=analysis["questions"],
            acoes_executadas=actions,
            artefatos_gerados=artifacts,
            caminho_de_saida=context["folders"]["processed"].as_posix(),
            extra={"metrics": metrics, "decisions": decisions, "limitations": limitations, "fallbacks": []},
        )

    def _run_with_timeout(self, func: Any, *args: Any) -> dict[str, Any]:
        timeout_seconds = max(10, min(self.settings.stage_timeout_seconds, 45))
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            return {
                "status": "partial",
                "findings": ["A etapa geométrica excedeu o orçamento operacional e foi encerrada em modo seguro."],
                "risks": ["A análise geométrica completa não terminou a tempo; valide o modelo no preview e no slicer."],
                "questions": [],
                "metrics": {"timed_out": True, "timeout_seconds": timeout_seconds},
                "actions": ["Timeout operacional aplicado."],
                "output_file": "",
            }
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
