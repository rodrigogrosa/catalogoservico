from pathlib import Path
import sys


from app.schemas.project import ProcessProjectRequest
from app.services.agents.llm_strategy_agent import LlmStrategyAgent
from app.services.project_service import ProjectService


def test_processing_stage_plan_includes_llm_and_delivery_steps() -> None:
    service = ProjectService()
    stages = service.build_processing_stages(
        {
            "request": ProcessProjectRequest(),
            "source_ecosystem": "bambu_lab",
        }
    )
    keys = [stage["key"] for stage in stages]
    assert "llm_strategy" in keys
    assert "llm_regression" in keys
    assert "reports" in keys
    assert "qa" in keys


def test_update_stage_status_marks_completion() -> None:
    service = ProjectService()
    manifest = {"processing_stages": []}
    service.update_stage_status(manifest, "geometry", "Análise geométrica", "in_progress", "Executando análise.")
    service.update_stage_status(manifest, "geometry", "Análise geométrica", "completed", "Concluída.")
    stage = manifest["processing_stages"][0]
    assert stage["status"] == "completed"
    assert stage["started_at"] is not None
    assert stage["completed_at"] is not None


def test_llm_strategy_agent_skips_when_runtime_is_unavailable(tmp_path: Path) -> None:
    agent = LlmStrategyAgent()
    agent.llm.describe_runtime = lambda: {
        "enabled": True,
        "available": False,
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:7b",
    }
    result = agent.run(
        {
            "folders": {"reports": tmp_path},
            "geometry_metrics": {},
            "knowledge_rules": [],
            "project": {"name": "demo", "input_format": "3mf"},
            "request": ProcessProjectRequest(),
            "source_ecosystem": "bambu_lab",
        }
    )
    assert result["status"] == "skipped"
    assert "LLM local indisponivel" in result["achados"][0]
