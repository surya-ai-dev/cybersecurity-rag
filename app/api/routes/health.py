"""Health check route under /api/v1."""

from fastapi import APIRouter, Depends

from app.api.dependencies import RAGService, get_rag_service
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(service: RAGService = Depends(get_rag_service)) -> HealthResponse:
    """Return service readiness and active memory feature-flag status."""
    return service.health()
