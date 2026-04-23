from __future__ import annotations

import json
from typing import Any

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import LLM_REGRESSION_PROMPT
from app.services.local_llm_service import LocalLlmService


class LlmRegressionAgent(BaseAgent):
    name = "llm_regression_agent"
    prompt = LLM_REGRESSION_PROMPT

    def __init__(self) -> None:
        self.llm = LocalLlmService()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        runtime = self.llm.describe_runtime()
        agent_outputs = context.get("agent_outputs", [])
        deterministic_checks = [
            "validar geometria em 3MF exportado",
            "validar parametros Snapmaker Orca contra valores minimos exigidos",
            "confirmar suportes quando houver overhangs sem apoio",
            "confirmar adesao de primeira camada quando a area de contato for reduzida",
        ]

        if not runtime["available"]:
            return self.result(
                status="skipped",
                etapa="checagem_local_de_regressao",
                achados=["Checklist de regressao caiu para modo deterministico por falta do LLM local."],
                riscos=[],
                perguntas_ao_usuario=[],
                acoes_executadas=deterministic_checks,
                artefatos_gerados=[],
                caminho_de_saida=context["folders"]["reports"].as_posix(),
                extra={"llm_runtime": runtime},
            )

        compact_outputs = [
            {
                "etapa": item.get("etapa"),
                "status": item.get("status"),
                "achados": item.get("achados", [])[:3],
                "riscos": item.get("riscos", [])[:3],
                "acoes_executadas": item.get("acoes_executadas", [])[:3],
            }
            for item in agent_outputs[:6]
        ]
        user_prompt = (
            "Responda JSON com chaves checks, riscos e acoes.\n"
            f"Saidas dos agentes: {json.dumps(compact_outputs, ensure_ascii=False)}\n"
            f"Regras de conhecimento: {json.dumps(context.get('knowledge_rules', [])[:6], ensure_ascii=False)}\n"
        )
        response = self.llm.generate_json(
            system_prompt=self.prompt,
            user_prompt=user_prompt,
            fallback={"checks": deterministic_checks, "riscos": [], "acoes": deterministic_checks},
        )
        checks = response.get("checks", [])[:6] or deterministic_checks
        return self.result(
            status="ok",
            etapa="checagem_local_de_regressao",
            achados=checks,
            riscos=response.get("riscos", [])[:5],
            perguntas_ao_usuario=[],
            acoes_executadas=response.get("acoes", [])[:6] or deterministic_checks,
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["reports"].as_posix(),
            extra={"llm_runtime": runtime, "llm_regression": response},
        )
