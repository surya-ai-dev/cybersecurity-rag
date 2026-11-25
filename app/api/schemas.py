"""Pydantic v2 request and response schemas for the Cybersecurity RAG HTTP API."""

from typing import List, Optional, Union
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Service health and active memory feature-flag status."""

    status: str
    persistent_memory_enabled: bool
    summarization_enabled: bool
    long_term_memory_enabled: bool
    active_session_id: Optional[str] = None


class SourceChunkDTO(BaseModel):
    """Retrieved document chunk formatted for frontend citation linking."""

    source_index: int
    chunk_id: str
    doc_id: str
    title: str
    section: str
    page: Optional[Union[int, str]] = None
    score: float = 0.0
    text_preview: str = ""


class UserPreferencesDTO(BaseModel):
    """Optional user response style, formatting, and focus lens preferences."""

    detail_level: Optional[str] = None
    response_format: Optional[str] = None
    focus_lens: Optional[str] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=500)


class ChatRequest(BaseModel):
    """Incoming user question scoped optionally to an existing session."""

    question: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    preferences: Optional[UserPreferencesDTO] = None


class MemoryFactDTO(BaseModel):
    """Serialized cybersecurity standard, control, or environment scope fact."""

    fact_id: str
    category: str
    key: str
    value: str
    source_turn: Optional[int] = None
    confidence: float = 1.0


class MemoryContextDTO(BaseModel):
    """Snapshot of the active three-tier memory state."""

    session_id: Optional[str] = None
    summary: str = ""
    active_facts: List[MemoryFactDTO] = Field(default_factory=list)
    recent_turn_count: int = 0


class ChatResponse(BaseModel):
    """Synchronous chat response payload."""

    session_id: str
    question: str
    standalone_question: str
    answer: str
    sources: List[SourceChunkDTO] = Field(default_factory=list)
    memory_context: MemoryContextDTO


class TurnDTO(BaseModel):
    """Persisted conversational turn returned for UI thread restoration."""

    turn_index: int
    user: str
    assistant: str
    standalone_question: Optional[str] = None
    source_chunk_ids: List[str] = Field(default_factory=list)
    timestamp: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """Optional metadata payload for creating a new session."""

    title: Optional[str] = None


class RenameSessionRequest(BaseModel):
    """Payload for renaming an existing conversation session."""

    title: str = Field(..., min_length=1, max_length=120)


class SessionSummaryDTO(BaseModel):
    """Lightweight session metadata for sidebar listing."""

    session_id: str
    title: str
    summary: str = ""
    turn_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class SessionDetailDTO(BaseModel):
    """Full persisted session state including chronological turns and facts."""

    session: SessionSummaryDTO
    turns: List[TurnDTO] = Field(default_factory=list)
    active_facts: List[MemoryFactDTO] = Field(default_factory=list)


class DeleteSessionResponse(BaseModel):
    """Confirmation payload returned after deleting a session."""

    deleted: bool
    session_id: str
