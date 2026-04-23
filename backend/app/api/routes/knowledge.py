from fastapi import APIRouter, Depends

from app.core.auth import require_current_user
from app.schemas.auth import AuthUser
from app.schemas.knowledge import (
    KnowledgeRuleListResponse,
    SlicerIncidentCreate,
    SlicerIncidentCreateResponse,
    SlicerIncidentListResponse,
)
from app.services.dependencies import get_knowledge_service
from app.services.knowledge_service import KnowledgeService


router = APIRouter()


@router.get("/rules", response_model=KnowledgeRuleListResponse)
async def list_rules(
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: AuthUser = Depends(require_current_user),
) -> KnowledgeRuleListResponse:
    _ = current_user
    return KnowledgeRuleListResponse(items=service.list_rules())


@router.get("/incidents", response_model=SlicerIncidentListResponse)
async def list_incidents(
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: AuthUser = Depends(require_current_user),
) -> SlicerIncidentListResponse:
    _ = current_user
    return SlicerIncidentListResponse(items=service.list_incidents())


@router.post("/incidents", response_model=SlicerIncidentCreateResponse)
async def create_incident(
    payload: SlicerIncidentCreate,
    service: KnowledgeService = Depends(get_knowledge_service),
    current_user: AuthUser = Depends(require_current_user),
) -> SlicerIncidentCreateResponse:
    _ = current_user
    incident, learned_actions = service.record_incident(payload)
    return SlicerIncidentCreateResponse(incident=incident, learned_actions=learned_actions)
