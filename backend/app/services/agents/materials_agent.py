from __future__ import annotations

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import MATERIALS_PROMPT


MATERIAL_GUIDE = {
    "PLA": {
        "nozzle": "190-220C",
        "bed": "45-60C",
        "strength": "média",
        "heat": "baixa",
        "drying": "geralmente opcional; 45C por 4h quando úmido",
        "safety": "baixo odor, ventilação básica suficiente",
        "abrasive": False,
        "notes": "fácil de imprimir, ideal para decorativo e protótipos",
    },
    "PETG": {
        "nozzle": "220-250C",
        "bed": "70-90C",
        "strength": "boa",
        "heat": "média",
        "drying": "65C por 4-6h quando úmido",
        "safety": "ventilação recomendada",
        "abrasive": False,
        "notes": "bom equilíbrio entre resistência, adesão entre camadas e facilidade",
    },
    "ASA": {
        "nozzle": "240-260C",
        "bed": "90-110C",
        "strength": "boa",
        "heat": "boa",
        "drying": "70C por 4-6h",
        "safety": "exige ventilação e ambiente mais controlado",
        "abrasive": False,
        "notes": "indicado para ambiente externo e UV, pede câmara mais controlada",
    },
    "TPU": {
        "nozzle": "210-240C",
        "bed": "40-60C",
        "strength": "flexível",
        "heat": "baixa-média",
        "drying": "45-55C por 4-6h",
        "safety": "ventilação básica suficiente",
        "abrasive": False,
        "notes": "bom para absorção de impacto e flexibilidade",
    },
    "PA-CF": {
        "nozzle": "260-300C",
        "bed": "70-100C",
        "strength": "alta",
        "heat": "alta",
        "drying": "80C por 8-12h",
        "safety": "ventilação forte, abrasivo e higroscópico",
        "abrasive": True,
        "notes": "alta rigidez e excelente uso funcional; higroscópico e abrasivo",
    },
    "PETG-CF": {
        "nozzle": "240-265C",
        "bed": "75-90C",
        "strength": "alta",
        "heat": "média",
        "drying": "65C por 6h",
        "safety": "ventilação recomendada; abrasivo",
        "abrasive": True,
        "notes": "mais rígido que PETG, bom para peças funcionais com baixa deformação",
    },
    "PA-GF": {
        "nozzle": "260-290C",
        "bed": "70-100C",
        "strength": "alta",
        "heat": "alta",
        "drying": "80C por 8-12h",
        "safety": "ventilação recomendada; abrasivo",
        "abrasive": True,
        "notes": "boa estabilidade dimensional, abrasivo e sensível à umidade",
    },
    "PC": {
        "nozzle": "270-310C",
        "bed": "100-120C",
        "strength": "alta",
        "heat": "alta",
        "drying": "80-90C por 6-8h",
        "safety": "requer máquina e ambiente muito controlados",
        "abrasive": False,
        "notes": "alto desempenho térmico, impressão difícil sem controle",
    },
    "PC-ABS": {
        "nozzle": "260-290C",
        "bed": "95-115C",
        "strength": "alta",
        "heat": "alta",
        "drying": "80C por 6h",
        "safety": "ventilação forte recomendada",
        "abrasive": False,
        "notes": "equilíbrio entre rigidez do PC e processabilidade do ABS",
    },
    "PP": {
        "nozzle": "220-250C",
        "bed": "85-110C",
        "strength": "média",
        "heat": "média",
        "drying": "opcional; baixa higroscopicidade",
        "safety": "ventilação recomendada",
        "abrasive": False,
        "notes": "ótima resistência química, adesão à mesa mais difícil",
    },
    "PVA": {
        "nozzle": "190-215C",
        "bed": "45-60C",
        "strength": "baixa",
        "heat": "baixa",
        "drying": "55C por 4-6h",
        "safety": "manter seco; suporte solúvel",
        "abrasive": False,
        "notes": "material de suporte solúvel em água, extremamente sensível à umidade",
    },
    "BVOH": {
        "nozzle": "190-220C",
        "bed": "45-60C",
        "strength": "baixa",
        "heat": "baixa",
        "drying": "55C por 4-6h",
        "safety": "manter seco; suporte solúvel",
        "abrasive": False,
        "notes": "suporte solúvel com melhor estabilidade que PVA, ainda muito higroscópico",
    },
    "HIPS": {
        "nozzle": "220-245C",
        "bed": "90-110C",
        "strength": "média",
        "heat": "média",
        "drying": "60C por 4h",
        "safety": "ventilação recomendada",
        "abrasive": False,
        "notes": "usado como suporte para ABS e peças leves, dissolução em limoneno",
    },
    "WOOD FILL": {
        "nozzle": "190-220C",
        "bed": "45-60C",
        "strength": "baixa-média",
        "heat": "baixa",
        "drying": "50C por 4h",
        "safety": "bico maior reduz entupimento",
        "abrasive": True,
        "notes": "acabamento decorativo, risco de entupimento em nozzle pequeno",
    },
    "METAL FILL": {
        "nozzle": "190-220C",
        "bed": "45-60C",
        "strength": "média",
        "heat": "baixa-média",
        "drying": "50C por 4h",
        "safety": "abrasivo; preferir nozzle endurecido",
        "abrasive": True,
        "notes": "visual metálico, pesado e abrasivo",
    },
    "GLOW": {
        "nozzle": "200-225C",
        "bed": "45-60C",
        "strength": "média",
        "heat": "baixa",
        "drying": "50C por 4h",
        "safety": "abrasivo; nozzle endurecido recomendado",
        "abrasive": True,
        "notes": "efeito visual luminoso, desgaste acelerado do bico",
    },
}


class MaterialsAgent(BaseAgent):
    name = "materials_agent"
    prompt = MATERIALS_PROMPT

    def run(self, context: dict[str, object]) -> dict[str, object]:
        request = context["request"]
        source_name = context["source_file"].stem.lower()
        prefs = request.material_preferences
        questions = []
        actions = []
        risks = []
        findings = []
        decisions = []
        assumed_use_case = prefs.use_case

        functional_keywords = ("stand", "holder", "mount", "dock", "rack", "adapter", "axle", "winder", "support")
        decorative_keywords = (
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

        if request.target_material:
            material = request.target_material.upper()
        elif prefs.use_case == "decorative":
            material = "PLA"
        elif prefs.flexibility_required:
            material = "TPU"
        elif prefs.outdoor_use:
            material = "ASA"
        elif prefs.thermal_resistance:
            material = "PC"
        elif prefs.use_case == "unknown" and any(keyword in source_name for keyword in functional_keywords):
            material = "PETG"
            assumed_use_case = "functional"
        elif prefs.use_case == "unknown" and any(keyword in source_name for keyword in decorative_keywords):
            material = "PLA"
            assumed_use_case = "decorative"
        else:
            material = "PETG"

        info = MATERIAL_GUIDE.get(material, MATERIAL_GUIDE["PETG"])
        actions.append(f"Material sugerido: {material}.")
        decisions.append(
            {
                "stage_key": "materials",
                "action": "recommend_material",
                "reason": "Regra de compatibilidade entre uso da peça, ambiente e perfil de impressão.",
                "impact": material,
                "destructive": False,
            }
        )
        if request.target_material is None:
            findings.append(
                f"Sem instruções explícitas de material, o agente assumiu uso {assumed_use_case} e selecionou {material} como padrão conservador."
            )
        if info["abrasive"]:
            risks.append("Material abrasivo; nozzle endurecido e diâmetro mínimo adequado são recomendados.")
        if material in {"ASA", "PC", "PC-ABS", "PA-CF", "PA-GF"}:
            risks.append("Material sugerido exige máquina e processo mais controlados do que um perfil FDM básico.")
        if prefs.use_case == "unknown" and request.target_material is None:
            risks.append("Material foi inferido automaticamente; confirme o uso real da peça antes de produção funcional crítica.")
            questions.append(
                {
                    "code": "material_use_case_confirmation",
                    "question": "A peça será decorativa, funcional ou estrutural?",
                    "reason": "A recomendação de material muda significativamente conforme a carga e o ambiente.",
                    "severity": "medium",
                    "kind": "recommended",
                }
            )

        findings.extend(
            [
                f"{material}: bico {info['nozzle']}, mesa {info['bed']}, resistência {info['strength']}, resistência térmica {info['heat']}.",
                f"Secagem e armazenamento: {info['drying']}.",
                f"Segurança operacional: {info['safety']}.",
                f"Aplicação recomendada: {info['notes']}.",
            ]
        )

        return self.result(
            status="ok",
            etapa="recomendacao_de_material",
            achados=findings,
            riscos=risks,
            perguntas_ao_usuario=questions,
            acoes_executadas=actions,
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["reports"].as_posix(),
            extra={"recommended_material": material, "profile_hint": info, "decisions": decisions, "fallbacks": [], "limitations": []},
        )
