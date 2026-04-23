from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


KnowledgeSeverity = Literal["low", "medium", "high"]


class KnowledgeRule(BaseModel):
    rule_id: str
    title: str
    description: str
    trigger_patterns: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    preventive_actions: list[str] = Field(default_factory=list)
    severity: KnowledgeSeverity = "medium"
    times_triggered: int = 0
    last_matched_at: datetime | None = None


class KnowledgeRuleListResponse(BaseModel):
    items: list[KnowledgeRule]


class IncidentMatch(BaseModel):
    rule_id: str
    title: str
    severity: KnowledgeSeverity
    preventive_actions: list[str] = Field(default_factory=list)


class SlicerIncidentCreate(BaseModel):
    project_id: str | None = None
    slicer: str = "snapmaker_orca"
    file_label: str | None = None
    errors: list[str] = Field(default_factory=list)
    notes: str | None = None


class SlicerIncidentRecord(BaseModel):
    incident_id: str
    created_at: datetime
    slicer: str
    project_id: str | None = None
    file_label: str | None = None
    errors: list[str] = Field(default_factory=list)
    notes: str | None = None
    matched_rules: list[IncidentMatch] = Field(default_factory=list)


class SlicerIncidentListResponse(BaseModel):
    items: list[SlicerIncidentRecord]


class SlicerIncidentCreateResponse(BaseModel):
    incident: SlicerIncidentRecord
    learned_actions: list[str] = Field(default_factory=list)
