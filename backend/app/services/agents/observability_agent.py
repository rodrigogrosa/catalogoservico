from __future__ import annotations

from typing import Any

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import OBSERVABILITY_PROMPT


class ObservabilityAgent(BaseAgent):
    name = "observability_agent"
    prompt = OBSERVABILITY_PROMPT

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        parser_result = context.get("parser_result", {})
        findings = []
        decisions = []
        if parser_result.get("warnings"):
            findings.append(f"{len(parser_result['warnings'])} avisos de parsing foram registrados.")
        if context.get("knowledge_rules"):
            findings.append(f"{len(context['knowledge_rules'])} regras de conhecimento foram aplicadas.")
        decisions.append(
            {
                "stage_key": "observability",
                "action": "capture_snapshot_context",
                "reason": "Toda execução precisa ser reproduzível e auditável.",
                "impact": "snapshot e trilha de decisão",
                "destructive": False,
            }
        )
        return self.result(
            status="ok",
            etapa="auditoria_e_observabilidade",
            achados=findings or ["Contexto de auditoria consolidado para snapshot final."],
            riscos=[],
            perguntas_ao_usuario=[],
            acoes_executadas=["Preparação de dados de auditoria e observabilidade concluída."],
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["reports"].as_posix(),
            extra={"decisions": decisions, "limitations": [], "fallbacks": []},
        )
