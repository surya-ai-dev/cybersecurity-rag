"""Synchronous and SSE streaming chat routes under /api/v1."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import RAGService, get_rag_service
from app.api.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: RAGService = Depends(get_rag_service),
) -> ChatResponse:
    """Execute a synchronous RAG query within the target or newly created session."""
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    return await service.chat(
        question=payload.question,
        session_id=payload.session_id,
        preferences=payload.preferences,
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    service: RAGService = Depends(get_rag_service),
) -> StreamingResponse:
    """Execute a streaming RAG query emitting Server-Sent Events (SSE)."""
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be blank.")
    return StreamingResponse(
        service.chat_stream(
            question=payload.question,
            session_id=payload.session_id,
            preferences=payload.preferences,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
