from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.storage_service import StorageService


class ReportService:
    def __init__(self) -> None:
        self.storage = StorageService()

    def write_report_bundle(self, reports_dir: Path, payload: dict[str, Any]) -> list[dict[str, str]]:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        json_path = reports_dir / f"technical_report_{timestamp}.json"
        md_path = reports_dir / f"technical_report_{timestamp}.md"
        self.storage.write_json(json_path, payload)
        md_path.write_text(self.render_markdown(payload), encoding="utf-8")
        return [
            {"label": "Relatorio tecnico JSON", "path": self.storage.to_storage_url(json_path), "kind": "report"},
            {"label": "Relatorio tecnico Markdown", "path": self.storage.to_storage_url(md_path), "kind": "report"},
        ]

    def render_markdown(self, payload: dict[str, Any]) -> str:
        lines = [
            "# SnapMaker3d Studio - Relatorio Tecnico",
            "",
            f"- Status: {payload.get('status', 'unknown')}",
            f"- Etapa: {payload.get('etapa', 'n/a')}",
            "",
            "## Achados",
        ]
        for item in payload.get("achados", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Riscos")
        for item in payload.get("riscos", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Perguntas ao usuario")
        for item in payload.get("perguntas_ao_usuario", []):
            lines.append(f"- {item.get('question')}")
        lines.append("")
        lines.append("## Acoes executadas")
        for item in payload.get("acoes_executadas", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Artefatos gerados")
        for item in payload.get("artefatos_gerados", []):
            lines.append(f"- {item}")
        lines.append("")
        if payload.get("knowledge_rules"):
            lines.append("## Conhecimento aplicado")
            for item in payload.get("knowledge_rules", []):
                lines.append(f"- {item.get('title', item.get('rule_id', 'regra'))}")
            lines.append("")
        lines.append(f"## Caminho de saida\n`{payload.get('caminho_de_saida', '')}`")
        return "\n".join(lines)
