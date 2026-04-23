from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.agents.bambu_agent import BambuAgent
from app.services.agents.colors_agent import ColorsAgent
from app.services.agents.geometry_agent import GeometryAgent
from app.services.agents.knowledge_agent import KnowledgeAgent
from app.services.agents.llm_regression_agent import LlmRegressionAgent
from app.services.agents.llm_strategy_agent import LlmStrategyAgent
from app.services.agents.materials_agent import MaterialsAgent
from app.services.agents.observability_agent import ObservabilityAgent
from app.services.agents.snapmaker_agent import SnapmakerAgent
from app.services.agents.transformation_agent import TransformationAgent


class OrchestratorAgent:
    def __init__(self) -> None:
        self.geometry_agent = GeometryAgent()
        self.knowledge_agent = KnowledgeAgent()
        self.llm_strategy_agent = LlmStrategyAgent()
        self.snapmaker_agent = SnapmakerAgent()
        self.transformation_agent = TransformationAgent()
        self.bambu_agent = BambuAgent()
        self.materials_agent = MaterialsAgent()
        self.colors_agent = ColorsAgent()
        self.llm_regression_agent = LlmRegressionAgent()
        self.observability_agent = ObservabilityAgent()

    def describe_pipeline(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        pipeline = [
            {"key": "geometry", "label": "Análise geométrica", "agent": self.geometry_agent},
            {"key": "knowledge", "label": "Conhecimento acumulado", "agent": self.knowledge_agent},
            {"key": "llm_strategy", "label": "Planejamento com LLM local", "agent": self.llm_strategy_agent},
        ]

        if context["request"].adapt_to_snapmaker:
            pipeline.append({"key": "snapmaker", "label": "Ajuste para Snapmaker U1", "agent": self.snapmaker_agent})

        pipeline.append({"key": "transformation", "label": "Transformações geométricas", "agent": self.transformation_agent})

        if context["request"].convert_from_bambu and context["source_ecosystem"] == "bambu_lab":
            pipeline.append({"key": "bambu", "label": "Conversão Bambu para Snapmaker", "agent": self.bambu_agent})

        pipeline.extend(
            [
                {"key": "materials", "label": "Estratégia de materiais", "agent": self.materials_agent},
                {"key": "colors", "label": "Estratégia de cores", "agent": self.colors_agent},
                {"key": "llm_regression", "label": "Checklist de regressão", "agent": self.llm_regression_agent},
                {"key": "observability", "label": "Auditoria e observabilidade", "agent": self.observability_agent},
            ]
        )
        return pipeline

    def run(
        self,
        context: dict[str, Any],
        progress_callback: Callable[[str, str, str, str | None], None] | None = None,
    ) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        context["agent_outputs"] = outputs

        for stage in self.describe_pipeline(context):
            if progress_callback:
                progress_callback(stage["key"], stage["label"], "in_progress", f"Executando {stage['label'].lower()}.")
            output = stage["agent"].run(context)
            outputs.append(output)
            if stage["key"] == "geometry":
                context["geometry_metrics"] = output.get("extra", {}).get("metrics", {})
            if stage["key"] == "transformation" and output["artefatos_gerados"]:
                context["transformed_artifacts"] = output["artefatos_gerados"]
            if progress_callback:
                progress_callback(
                    stage["key"],
                    stage["label"],
                    self._map_stage_status(output["status"]),
                    self._summarize_output(output),
                )

        pending_questions = [question for output in outputs for question in output["perguntas_ao_usuario"]]
        context["pending_questions"] = pending_questions
        return outputs

    def _map_stage_status(self, output_status: str) -> str:
        if output_status == "failed":
            return "failed"
        if output_status == "skipped":
            return "skipped"
        return "completed"

    def _summarize_output(self, output: dict[str, Any]) -> str:
        if output["acoes_executadas"]:
            return output["acoes_executadas"][0]
        if output["achados"]:
            return output["achados"][0]
        if output["riscos"]:
            return output["riscos"][0]
        return output["etapa"]

    def collect_prompts(self) -> dict[str, str]:
        return {
            "geometry_agent": self.geometry_agent.prompt,
            "knowledge_agent": self.knowledge_agent.prompt,
            "llm_strategy_agent": self.llm_strategy_agent.prompt,
            "snapmaker_agent": self.snapmaker_agent.prompt,
            "transformation_agent": self.transformation_agent.prompt,
            "bambu_agent": self.bambu_agent.prompt,
            "materials_agent": self.materials_agent.prompt,
            "colors_agent": self.colors_agent.prompt,
            "llm_regression_agent": self.llm_regression_agent.prompt,
            "observability_agent": self.observability_agent.prompt,
        }
