from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from app.core.config import get_settings
from app.services.agents.base import BaseAgent
from app.services.agents.prompts import BAMBU_PROMPT
from app.services.conversion_service import ConversionService


class BambuAgent(BaseAgent):
    name = "bambu_conversion_agent"
    prompt = BAMBU_PROMPT

    def __init__(self) -> None:
        self.conversion = ConversionService()
        self.settings = get_settings()

    def run(self, context: dict[str, object]) -> dict[str, object]:
        source_file = context["source_file"]
        inspection = self.conversion.inspect_bambu_project(source_file)
        context["bambu_detected_items"] = inspection.get("detected_items", [])
        conversion = self._convert_with_timeout(
            source_file,
            context["folders"]["export"],
            context.get("support_plan"),
            context.get("adhesion_plan"),
            context["request"].scale_mode,
        )

        findings = inspection["findings"] + [f"Itens detectados: {', '.join(inspection.get('detected_items', [])) or 'nenhum'}."]
        if conversion.get("parameter_equivalence"):
            findings.append(f"Equivalência auditável gerada para {len(conversion['parameter_equivalence'])} parâmetros.")
        artifacts = [conversion["output_file"]] if conversion.get("output_file") else []

        return self.result(
            status="partial" if conversion.get("output_file") else "failed",
            etapa="conversao_bambu_para_snapmaker",
            achados=findings,
            riscos=["Compatibilidade perfeita com parâmetros proprietários do Bambu Studio não é presumida."],
            perguntas_ao_usuario=[],
            acoes_executadas=[
                "Inspeção do pacote Bambu/3MF concluída.",
                "Artefato compatível base para fluxo Snapmaker gerado." if artifacts else "Conversão interrompida com fallback seguro.",
            ],
            artefatos_gerados=artifacts,
            caminho_de_saida=context["folders"]["export"].as_posix(),
            extra={
                "preserved": conversion["preserved"],
                "adapted": conversion["adapted"],
                "lost": conversion["lost"],
                "support_plan": conversion.get("support_plan"),
                "adhesion_plan": conversion.get("adhesion_plan"),
                "parameter_equivalence": conversion.get("parameter_equivalence", []),
                "decisions": [
                    {
                        "stage_key": "bambu",
                        "action": "convert_to_snapmaker",
                        "reason": "Projeto Bambu/3MF detectado e convertido para fluxo Snapmaker Orca 2.3.0.",
                        "impact": "geração de um único 3MF compatível",
                        "destructive": False,
                    }
                ],
                "fallbacks": conversion.get("lost", []),
                "limitations": conversion.get("lost", []),
            },
        )

    def _convert_with_timeout(
        self,
        source_file: object,
        export_dir: object,
        support_plan: object,
        adhesion_plan: object,
        scale_mode: object,
    ) -> dict[str, object]:
        timeout_seconds = max(20, min(self.settings.stage_timeout_seconds, 90))
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self.conversion.convert_to_snapmaker,
            source_file,
            export_dir,
            support_plan=support_plan,
            adhesion_plan=adhesion_plan,
            scale_mode=scale_mode,
        )
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            return {
                "status": "failed",
                "output_file": "",
                "preserved": [],
                "adapted": [],
                "lost": [f"Conversão Bambu excedeu {timeout_seconds}s e foi interrompida em modo seguro."],
                "support_plan": support_plan or {"enabled": False},
                "adhesion_plan": adhesion_plan or {"mode": "skirt"},
                "parameter_equivalence": [],
            }
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
