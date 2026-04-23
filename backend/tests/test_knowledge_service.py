from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.schemas.knowledge import SlicerIncidentCreate
from app.services.knowledge_service import KnowledgeService


def test_records_incident_and_matches_seeded_rules(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNAPMAKER_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    service = KnowledgeService()

    incident, learned_actions = service.record_incident(
        SlicerIncidentCreate(
            project_id="demo_v001",
            slicer="snapmaker_orca",
            file_label="Deadpool 3 Mask plated",
            errors=[
                "One object has empty initial layer and can't be printed.",
                "Invalid values found in the 3mf: prime_tower_width: 0 not in range [2,2147483647]",
                "Model too close to bed boundary. keep at least 3.5mm gap to avoid collision.",
            ],
        )
    )

    assert incident.project_id == "demo_v001"
    assert len(incident.matched_rules) >= 3
    assert any(match.rule_id == "orca_empty_initial_layer_ground_build_items" for match in incident.matched_rules)
    assert any(match.rule_id == "orca_prime_tower_width_minimum" for match in incident.matched_rules)
    assert any("prime_tower_width" in action or "Z=0" in action for action in learned_actions)
