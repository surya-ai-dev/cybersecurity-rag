"""Session management and memory inspection routes under /api/v1."""

from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.api.dependencies import RAGService, get_rag_service
from app.api.schemas import (
    CreateSessionRequest,
    DeleteSessionResponse,
    RenameSessionRequest,
    SessionDetailDTO,
    SessionSummaryDTO,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummaryDTO)
async def create_session(
    payload: Optional[CreateSessionRequest] = Body(default=None),
    service: RAGService = Depends(get_rag_service),
) -> SessionSummaryDTO:
    """Create a new persisted conversation session."""
    title = payload.title if payload is not None else None
    return await service.create_session(title=title)


@router.get("", response_model=List[SessionSummaryDTO])
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=200),
    service: RAGService = Depends(get_rag_service),
) -> List[SessionSummaryDTO]:
    """List saved conversation sessions ordered by most recently updated."""
    return await service.list_sessions(limit=limit)


@router.get("/{session_id}", response_model=SessionDetailDTO)
async def get_session(
    session_id: str,
    service: RAGService = Depends(get_rag_service),
) -> SessionDetailDTO:
    """Fetch complete persisted turns, summary, and active facts for a session."""
    detail = await service.get_session_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return detail


@router.patch("/{session_id}", response_model=SessionSummaryDTO)
async def rename_session(
    session_id: str,
    payload: RenameSessionRequest,
    service: RAGService = Depends(get_rag_service),
) -> SessionSummaryDTO:
    """Rename a persisted conversation session."""
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="Title cannot be blank.")
    updated = await service.rename_session(session_id, payload.title)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return updated


@router.post("/{session_id}/clear", response_model=SessionSummaryDTO)
async def clear_session(
    session_id: str,
    service: RAGService = Depends(get_rag_service),
) -> SessionSummaryDTO:
    """Clear turns, summary, and facts for an existing session."""
    summary = await service.clear_session(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return summary


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(
    session_id: str,
    service: RAGService = Depends(get_rag_service),
) -> DeleteSessionResponse:
    """Delete a session and cascade-remove its turns, facts, and embeddings."""
    deleted = await service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return DeleteSessionResponse(deleted=True, session_id=session_id)
