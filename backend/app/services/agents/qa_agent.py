from __future__ import annotations

from pathlib import Path

from app.services.agents.base import BaseAgent
from app.services.agents.prompts import QA_PROMPT


class QATechnicalAgent(BaseAgent):
    name = "qa_technical_agent"
    prompt = QA_PROMPT

    def run(self, context: dict[str, object]) -> dict[str, object]:
        findings = []
        risks = []
        actions = ["Checklist de entrega executado."]
        decisions = []

        required_dirs = ["original", "processed", "export", "reports", "previews", "logs"]
        for key in required_dirs:
            folder = context["folders"][key]
            if not Path(folder).exists():
                risks.append(f"Pasta obrigatória ausente: {folder}")

        if not context.get("report_artifacts"):
            risks.append("Nenhum relatório técnico foi gerado.")
        else:
            findings.append("Relatórios técnicos presentes.")

        support_plan = context.get("support_plan") or {}
        adhesion_plan = context.get("adhesion_plan") or {}
        geometry_metrics = context.get("geometry_metrics") or {}
        if geometry_metrics.get("support_required") and not support_plan.get("enabled"):
            risks.append("A geometria exige suportes, mas o plano final não os ativou.")
        if geometry_metrics.get("adhesion_mode") in {"brim", "raft"} and adhesion_plan.get("mode") not in {"brim", "raft"}:
            risks.append("A geometria pede reforço de primeira camada, mas o plano final não o preservou.")
        if adhesion_plan.get("mode") in {"brim", "raft"}:
            findings.append(f"Plano de primeira camada presente: {adhesion_plan['mode']}.")
        if geometry_metrics.get("recommended_orientation"):
            findings.append(f"Orientação sugerida no pipeline: {geometry_metrics['recommended_orientation']}.")

        if context.get("pending_questions"):
            risks.append("Existem perguntas pendentes; resultado não deve ser tratado como definitivo.")

        printable_score = self._build_printable_score(findings, risks, context)
        if printable_score["blockers"]:
            decisions.append(
                {
                    "stage_key": "qa",
                    "action": "block_final_delivery",
                    "reason": "Existem bloqueantes técnicos ou perguntas obrigatórias em aberto.",
                    "impact": "awaiting_user",
                    "destructive": False,
                }
            )

        before_after = {
            "original_faces": context.get("project", {}).get("metadata", {}).get("mesh_metrics", {}).get("faces"),
            "processed_orientation": geometry_metrics.get("recommended_orientation"),
            "support_plan": support_plan,
            "adhesion_plan": adhesion_plan,
            "questions_pending": len(context.get("pending_questions") or []),
        }

        return self.result(
            status="ok" if not risks else "partial",
            etapa="qa_tecnico",
            achados=findings,
            riscos=risks,
            perguntas_ao_usuario=[],
            acoes_executadas=actions,
            artefatos_gerados=[],
            caminho_de_saida=context["folders"]["root"].as_posix(),
            extra={
                "printable_score": printable_score,
                "before_after_diff": before_after,
                "decisions": decisions,
                "limitations": [],
                "fallbacks": [],
            },
        )

    def _build_printable_score(self, findings: list[str], risks: list[str], context: dict[str, object]) -> dict[str, object]:
        blocking_questions = [
            question["question"]
            for question in (context.get("pending_questions") or [])
            if question.get("kind") == "blocking" or question.get("severity") == "high"
        ]
        score = 100 - (len(risks) * 12) - (len(blocking_questions) * 15)
        score = max(0, min(100, score))
        level = "low" if score >= 80 else "medium" if score >= 55 else "high"
        recommendations = []
        if any("suporte" in risk.lower() for risk in risks):
            recommendations.append("Revisar estratégia de suporte antes de imprimir.")
        if any("primeira camada" in risk.lower() for risk in risks):
            recommendations.append("Revisar aderência inicial, brim/raft e preparação da mesa.")
        if not recommendations and risks:
            recommendations.append("Revisar riscos remanescentes antes da produção.")
        return {
            "score": score,
            "level": level,
            "blockers": blocking_questions,
            "warnings": risks[:10],
            "recommendations": recommendations,
        }
