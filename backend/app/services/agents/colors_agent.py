from __future__ import annotations

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import COLORS_PROMPT


class ColorsAgent(BaseAgent):
    name = "colors_agent"
    prompt = COLORS_PROMPT

    def run(self, context: dict[str, object]) -> dict[str, object]:
        request = context["request"]
        prefs = request.color_preferences
        source_name = context["source_file"].stem.lower()
        detected_items = set(context.get("bambu_detected_items", []))
        parser_metadata = context.get("parser_result", {}).get("metadata", {})
        findings = []
        questions = []
        actions = []
        decisions = []
        likely_character = any(
            keyword in source_name
            for keyword in (
                "mario",
                "pokemon",
                "charizard",
                "deadpool",
                "donald",
                "grogu",
                "goku",
                "goofy",
                "yoshi",
                "luigi",
                "peach",
                "spiderman",
                "superman",
                "mickey",
                "toad",
                "piranha",
            )
        )
        effective_strategy = prefs.strategy
        if effective_strategy == "undecided":
            if "multicolor_data" in detected_items:
                effective_strategy = "split_parts"
            elif parser_metadata.get("texture_intent_detected"):
                effective_strategy = "paint_after"
            else:
                effective_strategy = "monochrome"

        if prefs.preserve_original_colors:
            findings.append("Fluxo configurado para preservar cores originais sempre que houver referência interna confiável.")
        if "multicolor_data" in detected_items:
            findings.append("Dados multicolor do projeto original foram detectados; a exportação priorizou preservar separação por partes.")
        if parser_metadata.get("texture_intent_detected"):
            findings.append("OBJ/MTL/texturas foram detectados; materiais e texturas foram tratados como sinal de intenção de cor.")
        if likely_character and prefs.character_variant is None:
            questions.append(
                {
                    "code": "character_variant",
                    "question": "Qual variante visual do personagem deve ser considerada como referência final?",
                    "reason": "O projeto parece representar um personagem conhecido e há risco de variação visual legítima.",
                    "severity": "medium",
                    "kind": "recommended",
                }
            )
        if effective_strategy == "paint_after":
            findings.append("Estratégia de cor definida para pintura posterior com preservação da forma.")
        elif effective_strategy == "split_parts":
            findings.append("Estratégia de cor definida para partes separadas por região/cor quando viável.")
        elif effective_strategy == "multicolor":
            findings.append("Estratégia de cor definida para fluxo multicolor.")
        else:
            findings.append("Estratégia de cor definida para versão monocromática fiel à forma.")

        actions.append(f"Estratégia de cor registrada: {effective_strategy}.")
        decisions.append(
            {
                "stage_key": "colors",
                "action": "select_color_strategy",
                "reason": "Estratégia escolhida a partir do projeto, texturas e preferências explícitas.",
                "impact": effective_strategy,
                "destructive": False,
            }
        )
        return self.result(
            status="ok",
            etapa="tratamento_de_cores",
            achados=findings,
            riscos=["Não assumir referência oficial de cor sem base visual suficiente."],
            perguntas_ao_usuario=questions,
            acoes_executadas=actions,
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["processed"].as_posix(),
            extra={"effective_strategy": effective_strategy, "decisions": decisions, "fallbacks": [], "limitations": []},
        )
