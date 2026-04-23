from __future__ import annotations

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import KNOWLEDGE_PROMPT
from app.services.knowledge_service import KnowledgeService


class KnowledgeAgent(BaseAgent):
    name = "knowledge_agent"
    prompt = KNOWLEDGE_PROMPT

    def __init__(self) -> None:
        self.knowledge = KnowledgeService()

    def run(self, context: dict[str, object]) -> dict[str, object]:
        summary = self.knowledge.summarize_for_context(context)
        matched_rules = summary["matched_rules"]
        context["knowledge_rules"] = [rule.model_dump(mode="json") for rule in matched_rules]
        return self.result(
            status="ok",
            etapa="aplicacao_de_conhecimento_operacional",
            achados=summary["knowledge_findings"] or ["Nenhuma regra operacional adicional foi acionada para este projeto."],
            riscos=[],
            perguntas_ao_usuario=[],
            acoes_executadas=summary["preventive_actions"] or ["Nenhuma acao preventiva adicional foi requerida pela base de conhecimento."],
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["reports"].as_posix(),
            extra={"knowledge_rules": context["knowledge_rules"]},
        )
