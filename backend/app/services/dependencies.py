from functools import lru_cache

from app.services.knowledge_service import KnowledgeService
from app.services.project_service import ProjectService


@lru_cache
def get_project_service() -> ProjectService:
    return ProjectService()


@lru_cache
def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()
