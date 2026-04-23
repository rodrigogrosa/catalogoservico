from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.knowledge import (
    IncidentMatch,
    KnowledgeRule,
    SlicerIncidentCreate,
    SlicerIncidentRecord,
)


SEED_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "orca_prime_tower_width_minimum",
        "title": "Prime tower width precisa respeitar o minimo do Orca",
        "description": "Quando o perfil desliga prime tower, ainda assim o Orca pode validar o campo e exigir largura minima.",
        "trigger_patterns": [r"prime_tower_width", r"Invalid values found in the 3mf"],
        "tags": ["orca", "3mf", "prime-tower", "bambu-conversion"],
        "preventive_actions": [
            "Definir prime_tower_width para o menor valor aceito pelo slicer em vez de zero absoluto.",
            "Desligar enable_prime_tower e neutralizar wipe/prime tower proprietarios do Bambu.",
        ],
        "severity": "high",
    },
    {
        "rule_id": "orca_empty_initial_layer_ground_build_items",
        "title": "Itens do build precisam estar assentados em Z=0",
        "description": "Projetos 3MF com transforms herdados do Bambu podem chegar ao Orca com camada inicial vazia se o build estiver flutuando.",
        "trigger_patterns": [r"empty initial layer", r"can't be printed", r"Cut the bottom or enable supports"],
        "tags": ["orca", "3mf", "initial-layer", "build-transform"],
        "preventive_actions": [
            "Recalcular bounds transformados do build e deslocar cada item para Z=0.",
            "Separar plates em exports independentes quando a composição inteira não couber na mesa da Snapmaker.",
        ],
        "severity": "high",
    },
    {
        "rule_id": "orca_boundary_margin_and_split",
        "title": "Arrangement precisa respeitar margem da cama",
        "description": "Placas importadas do Bambu podem ficar próximas demais da borda e provocar aviso de colisão ou slicing inconsistente.",
        "trigger_patterns": [r"bed boundary", r"keep at least 3.5mm gap", r"collision"],
        "tags": ["orca", "bed-layout", "split", "clearance"],
        "preventive_actions": [
            "Recentralizar itens no envelope útil da U1 com margem minima.",
            "Dividir o layout em múltiplos arquivos quando a área total exceder a cama.",
        ],
        "severity": "high",
    },
    {
        "rule_id": "fdm_supports_for_floating_regions",
        "title": "Regiões flutuantes exigem suporte vindo da mesa",
        "description": "Pontos sem apoio e regiões suspensas devem acionar suportes automáticos e preferência por build plate only.",
        "trigger_patterns": [r"floating regions", r"enable support", r"supports"],
        "tags": ["support", "overhang", "orca", "fdm"],
        "preventive_actions": [
            "Ativar suporte automático para overhangs críticos.",
            "Preferir suporte saindo da mesa quando a orientação permitir.",
        ],
        "severity": "high",
    },
    {
        "rule_id": "first_layer_adhesion_is_not_optional",
        "title": "Primeira camada precisa de estratégia ativa de adesão",
        "description": "Peças com área de contato pequena, alta ou esbelta devem usar brim ou raft e parâmetros de primeira camada mais conservadores.",
        "trigger_patterns": [r"first layer", r"adhesion", r"raft", r"brim"],
        "tags": ["adhesion", "first-layer", "raft", "brim"],
        "preventive_actions": [
            "Calcular área real de contato com a mesa.",
            "Aplicar skirt, brim ou raft conforme o risco geométrico.",
        ],
        "severity": "high",
    },
    {
        "rule_id": "relative_extrusion_and_layer_reset",
        "title": "Perfis Bambu com extrusão relativa precisam ser neutralizados",
        "description": "O Snapmaker Orca pode rejeitar certos perfis relativos se o reset do extrusor por camada não estiver coerente.",
        "trigger_patterns": [r"relative extruder addressing", r"use_relative_e_distances", r"G92 E0"],
        "tags": ["gcode", "extrusion", "orca", "bambu-conversion"],
        "preventive_actions": [
            "Desativar use_relative_e_distances no export compatível.",
            "Injetar G92 E0 no layer change gcode quando necessário.",
        ],
        "severity": "high",
    },
]


class KnowledgeService:
    def __init__(self) -> None:
        settings = get_settings()
        self.root = settings.storage_root / "knowledge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.rules_path = self.root / "rules.json"
        self.incidents_path = self.root / "incidents.json"
        self._ensure_files()

    def list_rules(self) -> list[KnowledgeRule]:
        raw = json.loads(self.rules_path.read_text(encoding="utf-8"))
        return [KnowledgeRule(**item) for item in raw]

    def list_incidents(self) -> list[SlicerIncidentRecord]:
        raw = json.loads(self.incidents_path.read_text(encoding="utf-8"))
        return [SlicerIncidentRecord(**item) for item in raw]

    def record_incident(self, payload: SlicerIncidentCreate) -> tuple[SlicerIncidentRecord, list[str]]:
        rules = self.list_rules()
        haystack = "\n".join(payload.errors + ([payload.notes] if payload.notes else [])).lower()
        matched_rules: list[KnowledgeRule] = []

        for rule in rules:
            if any(re.search(pattern, haystack, re.IGNORECASE) for pattern in rule.trigger_patterns):
                rule.times_triggered += 1
                rule.last_matched_at = datetime.now(tz=timezone.utc)
                matched_rules.append(rule)

        self._save_rules(rules)

        incident = SlicerIncidentRecord(
            incident_id=f"incident_{uuid4().hex[:12]}",
            created_at=datetime.now(tz=timezone.utc),
            slicer=payload.slicer,
            project_id=payload.project_id,
            file_label=payload.file_label,
            errors=payload.errors,
            notes=payload.notes,
            matched_rules=[
                IncidentMatch(
                    rule_id=rule.rule_id,
                    title=rule.title,
                    severity=rule.severity,
                    preventive_actions=rule.preventive_actions,
                )
                for rule in matched_rules
            ],
        )
        incidents = self.list_incidents()
        incidents.insert(0, incident)
        self._save_incidents(incidents[:500])

        learned_actions = [
            action
            for rule in matched_rules
            for action in rule.preventive_actions
        ]
        if not learned_actions:
            learned_actions = [
                "Incidente registrado sem regra conhecida. Revise o erro e adicione um padrão preventivo ao repositório de conhecimento.",
            ]
        return incident, learned_actions

    def summarize_for_context(self, context: dict[str, Any]) -> dict[str, Any]:
        rules = self.list_rules()
        source_ecosystem = str(context.get("source_ecosystem", "unknown"))
        geometry_metrics = context.get("geometry_metrics") or {}
        request = context.get("request")
        matched: list[KnowledgeRule] = []

        for rule in rules:
            tags = set(rule.tags)
            if source_ecosystem == "bambu_lab" and "bambu-conversion" in tags:
                matched.append(rule)
                continue
            if geometry_metrics.get("support_required") and {"support", "overhang"} & tags:
                matched.append(rule)
                continue
            if geometry_metrics.get("adhesion_mode") in {"brim", "raft"} and {"adhesion", "first-layer", "raft", "brim"} & tags:
                matched.append(rule)
                continue
            extents = geometry_metrics.get("extents_mm_assumed") or []
            if extents and any(extent > limit for extent, limit in zip(extents, (270, 270, 270))) and {"bed-layout", "split"} & tags:
                matched.append(rule)
                continue
            if request and getattr(request, "adapt_to_snapmaker", False) and "orca" in tags and "gcode" in tags:
                matched.append(rule)

        deduped: dict[str, KnowledgeRule] = {rule.rule_id: rule for rule in matched}
        ordered = list(deduped.values())
        return {
            "matched_rules": ordered,
            "knowledge_findings": [f"Regra ativa: {rule.title}." for rule in ordered],
            "preventive_actions": [action for rule in ordered for action in rule.preventive_actions],
        }

    def _ensure_files(self) -> None:
        if not self.rules_path.exists():
            seed = [KnowledgeRule(**item).model_dump(mode="json") for item in SEED_RULES]
            self.rules_path.write_text(json.dumps(seed, indent=2, ensure_ascii=False), encoding="utf-8")
        if not self.incidents_path.exists():
            self.incidents_path.write_text("[]", encoding="utf-8")

    def _save_rules(self, rules: list[KnowledgeRule]) -> None:
        payload = [rule.model_dump(mode="json") for rule in rules]
        self.rules_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _save_incidents(self, incidents: list[SlicerIncidentRecord]) -> None:
        payload = [incident.model_dump(mode="json") for incident in incidents]
        self.incidents_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
