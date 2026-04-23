from __future__ import annotations

import json
from typing import Any

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import LLM_STRATEGY_PROMPT
from app.services.local_llm_service import LocalLlmService


class LlmStrategyAgent(BaseAgent):
    name = "llm_strategy_agent"
    prompt = LLM_STRATEGY_PROMPT

    def __init__(self) -> None:
        self.llm = LocalLlmService()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        runtime = self.llm.describe_runtime()
        if not runtime["available"]:
            return self.result(
                status="skipped",
                etapa="planejamento_local_com_llm",
                achados=["LLM local indisponivel; pipeline seguiu com heuristicas deterministicas."],
                riscos=[],
                perguntas_ao_usuario=[],
                acoes_executadas=["Nenhuma chamada ao Ollama foi executada nesta etapa."],
                artefatos_gerados=[],
                caminho_de_saida=context["folders"]["reports"].as_posix(),
                extra={"llm_runtime": runtime},
            )

        geometry_metrics = context.get("geometry_metrics", {})
        compact_metrics = {
            "bounding_box_mm": geometry_metrics.get("bounding_box_mm"),
            "is_watertight": geometry_metrics.get("is_watertight"),
            "connected_components": geometry_metrics.get("connected_components"),
            "has_thin_walls": bool(geometry_metrics.get("thin_wall_regions")),
            "has_microdetails": bool(geometry_metrics.get("microdetail_regions")),
            "overhang_risk": geometry_metrics.get("overhang_risk"),
            "first_layer_contact_ratio": geometry_metrics.get("first_layer_contact_ratio"),
        }
        compact_rules = context.get("knowledge_rules", [])[:6]
        compact_preferences = context["request"].model_dump(mode="json")
        user_prompt = (
            "Gere um plano curto em JSON com chaves achados, riscos, acoes, perguntas.\n"
            f"Projeto: {context['project']['name']}\n"
            f"Formato: {context['project']['input_format']}\n"
            f"Ecossistema: {context['source_ecosystem']}\n"
            f"Metricas geometricas: {json.dumps(compact_metrics, ensure_ascii=False)}\n"
            f"Regras conhecidas: {json.dumps(compact_rules, ensure_ascii=False)}\n"
            f"Preferencias de processamento: {json.dumps(compact_preferences, ensure_ascii=False)}\n"
        )
        response = self.llm.generate_json(
            system_prompt=self.prompt,
            user_prompt=user_prompt,
            fallback={
                "achados": [],
                "riscos": [],
                "acoes": [],
                "perguntas": [],
            },
        )
        questions = []
        for item in response.get("perguntas", [])[:3]:
            if not isinstance(item, dict) or not item.get("question"):
                continue
            questions.append(
                {
                    "code": item.get("code", "llm_strategy_question"),
                    "question": item["question"],
                    "reason": item.get("reason", "LLM local detectou ambiguidade relevante para a entrega."),
                    "severity": item.get("severity", "medium"),
                }
            )

        context["llm_strategy"] = response
        return self.result(
            status="ok",
            etapa="planejamento_local_com_llm",
            achados=response.get("achados", [])[:5],
            riscos=response.get("riscos", [])[:5],
            perguntas_ao_usuario=questions,
            acoes_executadas=response.get("acoes", [])[:5] or ["LLM local consolidou um plano de execucao conservador."],
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["reports"].as_posix(),
            extra={"llm_runtime": runtime, "llm_strategy": response},
        )
