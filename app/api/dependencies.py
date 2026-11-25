"""Shared RAGService dependency managing RAGEngine lifecycle and thread-safe session routing."""

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple
import uuid

from fastapi import Request

from app.api.schemas import (
    ChatResponse,
    HealthResponse,
    MemoryContextDTO,
    MemoryFactDTO,
    SessionDetailDTO,
    SessionSummaryDTO,
    SourceChunkDTO,
    TurnDTO,
)
from app.core.config import settings
from app.core.interfaces import BaseMemoryManager
from app.core.models import (
    ChunkMetadata,
    MemoryContext,
    MemoryFact,
    Message,
    RetrievedChunk,
    SessionMetadata,
)
from app.pipeline.engine import RAGEngine, _is_memory_manager


def format_sse(event: str, payload: Dict[str, Any]) -> str:
    """Format a Server-Sent Events (SSE) frame."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _extract_chunk_score(chunk: RetrievedChunk) -> float:
    for attr in ("reranker_score", "rrf_score", "dense_score", "bm25_score", "score"):
        val = getattr(chunk, attr, None)
        if val is not None:
            return float(val)
    return 0.0


def chunk_to_dto(index: int, chunk: RetrievedChunk) -> SourceChunkDTO:
    """Convert a RetrievedChunk into a frontend SourceChunkDTO."""
    meta = chunk.metadata if isinstance(chunk.metadata, ChunkMetadata) else ChunkMetadata()
    extra = meta.extra if isinstance(meta.extra, dict) else {}

    doc_id = str(meta.document_id or "Unknown")
    title = str(extra.get("title") or meta.source_file or doc_id)
    section = str(extra.get("section_heading") or meta.section or "Unknown")
    page = extra.get("page_start")
    if page is None:
        page = extra.get("page")

    raw_text = chunk.text or ""
    preview = raw_text[:400].strip()

    return SourceChunkDTO(
        source_index=index,
        chunk_id=str(chunk.chunk_id),
        doc_id=doc_id,
        title=title,
        section=section,
        page=page,
        score=_extract_chunk_score(chunk),
        text_preview=preview,
    )


def fact_to_dto(fact: MemoryFact) -> MemoryFactDTO:
    """Convert MemoryFact domain model into MemoryFactDTO."""
    return MemoryFactDTO(
        fact_id=fact.fact_id,
        category=fact.category,
        key=fact.key,
        value=fact.value,
        source_turn=fact.source_turn,
        confidence=float(fact.confidence),
    )


def memory_context_to_dto(ctx: MemoryContext) -> MemoryContextDTO:
    """Convert MemoryContext domain model into MemoryContextDTO."""
    return MemoryContextDTO(
        session_id=ctx.session_id,
        summary=ctx.summary,
        active_facts=[fact_to_dto(f) for f in ctx.active_facts],
        recent_turn_count=len(ctx.recent_messages),
    )


def session_meta_to_dto(meta: SessionMetadata) -> SessionSummaryDTO:
    """Convert SessionMetadata into SessionSummaryDTO."""
    return SessionSummaryDTO(
        session_id=meta.session_id,
        title=meta.title,
        summary=meta.summary,
        turn_count=meta.turn_count,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


def message_to_turn_dto(msg: Message, fallback_index: int) -> TurnDTO:
    """Convert Message domain model into TurnDTO."""
    return TurnDTO(
        turn_index=msg.turn_index if msg.turn_index is not None else fallback_index,
        user=msg.user,
        assistant=msg.assistant,
        standalone_question=msg.standalone_question,
        source_chunk_ids=list(msg.source_chunk_ids or []),
        timestamp=msg.timestamp,
    )


class RAGService:
    """Coordinates async HTTP/SSE access to a shared RAGEngine safely across requests."""

    def __init__(self, engine: Optional[RAGEngine] = None) -> None:
        self._engine: Optional[RAGEngine] = engine
        self._lock = asyncio.Lock()
        self._fallback_session_id: Optional[str] = None

    @property
    def engine(self) -> RAGEngine:
        if self._engine is None:
            self._engine = RAGEngine()
            # Ensure HTTP API service always uses durable SQLite persistence across restarts
            if not _is_memory_manager(self._engine.memory) or not getattr(
                self._engine.memory, "enable_persistence", False
            ):
                from app.conversation.memory_manager import MemoryManager

                self._engine.memory = MemoryManager(
                    llm_provider=self._engine.llm_provider,
                    enable_persistence=True,
                )
        return self._engine

    def startup(self) -> None:
        """Initialize the underlying RAGEngine if not yet created."""
        _ = self.engine

    def shutdown(self) -> None:
        """Cleanly release underlying RAGEngine, Qdrant, reranker, and SQLite connections."""
        if self._engine is not None:
            self._engine.close()

    def _has_memory_manager(self) -> bool:
        return _is_memory_manager(self.engine.memory)

    def _bind_session_sync(self, session_id: Optional[str]) -> str:
        """Switch to existing/target session or create a fresh one when omitted."""
        memory = self.engine.memory
        if self._has_memory_manager():
            clean_sid = session_id.strip() if session_id else ""
            if clean_sid:
                meta = memory.switch_session(clean_sid)  # type: ignore[attr-defined]
                return meta.session_id
            meta = memory.new_session()  # type: ignore[attr-defined]
            return meta.session_id

        # Fallback for simple in-memory ConversationMemory (unique per session)
        clean_sid = session_id.strip() if session_id else ""
        if not clean_sid:
            self._fallback_session_id = str(uuid.uuid4())
            return self._fallback_session_id
        self._fallback_session_id = clean_sid
        return clean_sid

    def _snapshot_memory_context_sync(self, query: str, session_id: str) -> MemoryContextDTO:
        memory = self.engine.memory
        if self._has_memory_manager():
            ctx = memory.get_context(query=query, session_id=session_id)  # type: ignore[attr-defined]
            return memory_context_to_dto(ctx)
        recent = memory.get_messages()
        return MemoryContextDTO(
            session_id=session_id,
            summary="",
            active_facts=[],
            recent_turn_count=len(recent),
        )

    def _prepare_retrieval_sync(self, question: str) -> Tuple[str, List[RetrievedChunk]]:
        """Run memory disambiguation + hybrid/adaptive retrieval + reranking synchronously."""
        history = self.engine._get_rewrite_context(question)
        standalone_question = self.engine._rewrite_query(question, history)
        final_chunks, _ = self.engine._retrieve_and_rank(standalone_question)
        return standalone_question, final_chunks

    def health(self) -> HealthResponse:
        memory = self.engine.memory
        if self._has_memory_manager():
            persistent = bool(getattr(memory, "enable_persistence", settings.enable_persistent_memory))
            summarization = bool(getattr(memory, "enable_summarization", settings.enable_memory_summarization))
            long_term = bool(getattr(memory, "enable_long_term", settings.enable_long_term_memory))
            active_sid = getattr(memory, "session_id", None)
        else:
            persistent = bool(settings.enable_persistent_memory)
            summarization = bool(settings.enable_memory_summarization)
            long_term = bool(settings.enable_long_term_memory)
            active_sid = None

        return HealthResponse(
            status="ok",
            persistent_memory_enabled=persistent,
            summarization_enabled=summarization,
            long_term_memory_enabled=long_term,
            active_session_id=active_sid,
        )

    async def chat(
        self,
        question: str,
        session_id: Optional[str] = None,
        preferences: Optional[Any] = None,
    ) -> ChatResponse:
        """Execute non-streaming RAG query under serialized session lock."""
        clean_question = question.strip()
        async with self._lock:
            target_sid = await asyncio.to_thread(self._bind_session_sync, session_id)
            if preferences is not None and isinstance(self.engine, RAGEngine):
                rag_response = await asyncio.to_thread(
                    self.engine.query, clean_question, False, preferences
                )
            else:
                rag_response = await asyncio.to_thread(self.engine.query, clean_question, False)
            source_dtos = [
                chunk_to_dto(idx, chunk)
                for idx, chunk in enumerate(rag_response.sources, start=1)
            ]
            mem_dto = await asyncio.to_thread(
                self._snapshot_memory_context_sync, clean_question, target_sid
            )
            return ChatResponse(
                session_id=target_sid,
                question=rag_response.question,
                standalone_question=rag_response.standalone_question,
                answer=rag_response.answer,
                sources=source_dtos,
                memory_context=mem_dto,
            )

    async def chat_stream(
        self,
        question: str,
        session_id: Optional[str] = None,
        preferences: Optional[Any] = None,
    ) -> AsyncIterator[str]:
        """Execute streaming RAG query emitting SSE events while holding session lock."""
        clean_question = question.strip()
        async with self._lock:
            try:
                target_sid = await asyncio.to_thread(self._bind_session_sync, session_id)
                yield format_sse("session", {"session_id": target_sid})

                if isinstance(self.engine, RAGEngine):
                    standalone_question, final_chunks = await asyncio.to_thread(
                        self._prepare_retrieval_sync, clean_question
                    )
                    source_dtos = [
                        chunk_to_dto(idx, chunk)
                        for idx, chunk in enumerate(final_chunks, start=1)
                    ]
                    yield format_sse(
                        "metadata",
                        {
                            "standalone_question": standalone_question,
                            "sources": [s.model_dump() for s in source_dtos],
                        },
                    )

                    context = self.engine.context_builder(final_chunks)
                    prompt = self.engine._build_prompt(
                        standalone_question, context, preferences=preferences
                    )

                    loop = asyncio.get_running_loop()
                    queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue()

                    def _stream_worker() -> None:
                        try:
                            for tok in self.engine.llm_provider.stream(
                                prompt,
                                temperature=settings.llm_temperature,
                                max_tokens=settings.llm_max_tokens,
                            ):
                                loop.call_soon_threadsafe(queue.put_nowait, ("token", tok))
                        except Exception as exc:
                            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
                        finally:
                            loop.call_soon_threadsafe(queue.put_nowait, ("end", None))

                    worker_future = asyncio.to_thread(_stream_worker)
                    worker_task = asyncio.create_task(worker_future)

                    collected_tokens: List[str] = []
                    stream_error: Optional[Exception] = None
                    try:
                        while True:
                            kind, payload = await queue.get()
                            if kind == "token":
                                collected_tokens.append(payload)
                                yield format_sse("token", {"token": payload})
                            elif kind == "error":
                                stream_error = payload
                                break
                            elif kind == "end":
                                break
                    finally:
                        await worker_task

                    if stream_error is not None:
                        yield format_sse("error", {"detail": str(stream_error)})
                        return

                    accumulated = "".join(collected_tokens)
                    if accumulated:
                        await asyncio.to_thread(
                            self.engine._record_turn,
                            clean_question,
                            accumulated,
                            standalone_question,
                            final_chunks,
                        )
                else:
                    # Fallback for standalone mocked engine with .stream()
                    yield format_sse(
                        "metadata",
                        {"standalone_question": clean_question, "sources": []},
                    )
                    loop = asyncio.get_running_loop()
                    queue = asyncio.Queue()

                    def _mock_worker() -> None:
                        try:
                            for tok in self.engine.stream(clean_question):
                                loop.call_soon_threadsafe(queue.put_nowait, ("token", tok))
                        except Exception as exc:
                            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
                        finally:
                            loop.call_soon_threadsafe(queue.put_nowait, ("end", None))

                    worker_task = asyncio.create_task(asyncio.to_thread(_mock_worker))
                    stream_error = None
                    try:
                        while True:
                            kind, payload = await queue.get()
                            if kind == "token":
                                yield format_sse("token", {"token": payload})
                            elif kind == "error":
                                stream_error = payload
                                break
                            elif kind == "end":
                                break
                    finally:
                        await worker_task

                    if stream_error is not None:
                        yield format_sse("error", {"detail": str(stream_error)})
                        return

                mem_dto = await asyncio.to_thread(
                    self._snapshot_memory_context_sync, clean_question, target_sid
                )
                yield format_sse(
                    "memory",
                    {
                        "summary": mem_dto.summary,
                        "active_facts": [f.model_dump() for f in mem_dto.active_facts],
                    },
                )
                yield format_sse("done", {"ok": True})
            except Exception as exc:
                yield format_sse("error", {"detail": str(exc)})

    async def create_session(self, title: Optional[str] = None) -> SessionSummaryDTO:
        async with self._lock:
            if self._has_memory_manager():
                meta = await asyncio.to_thread(self.engine.memory.new_session, title)  # type: ignore[attr-defined]
                return session_meta_to_dto(meta)

            now = datetime.now(timezone.utc).isoformat()
            return SessionSummaryDTO(
                session_id=str(uuid.uuid4()),
                title=title or "New Session",
                summary="",
                turn_count=0,
                created_at=now,
                updated_at=now,
            )

    async def list_sessions(self, limit: int = 20) -> List[SessionSummaryDTO]:
        async with self._lock:
            if self._has_memory_manager():
                sessions = await asyncio.to_thread(self.engine.memory.list_sessions, limit)  # type: ignore[attr-defined]
                return [session_meta_to_dto(s) for s in sessions]

            return []

    def _get_session_detail_sync(self, session_id: str) -> Optional[SessionDetailDTO]:
        memory = self.engine.memory
        if not self._has_memory_manager():
            if not self._fallback_session_id or session_id != self._fallback_session_id:
                return None
            msgs = memory.get_messages()
            turns = [message_to_turn_dto(m, idx) for idx, m in enumerate(msgs, start=1)]
            return SessionDetailDTO(
                session=SessionSummaryDTO(
                    session_id=self._fallback_session_id,
                    title="Session",
                    turn_count=len(turns),
                ),
                turns=turns,
                active_facts=[],
            )

        store = getattr(memory, "store", None)
        if store is not None:
            meta = store.get_session(session_id)
            if meta is None:
                return None
            raw_turns = store.get_session_turns(session_id, limit=100)
            turns = [message_to_turn_dto(m, idx) for idx, m in enumerate(raw_turns, start=1)]
            facts = store.get_facts(session_id=session_id)
            return SessionDetailDTO(
                session=session_meta_to_dto(meta),
                turns=turns,
                active_facts=[fact_to_dto(f) for f in facts],
            )

        # In-memory MemoryManager fallback
        if getattr(memory, "session_id", None) != session_id:
            return None
        ctx = memory.get_context(session_id=session_id)  # type: ignore[attr-defined]
        turns = [
            message_to_turn_dto(m, idx) for idx, m in enumerate(ctx.recent_messages, start=1)
        ]
        return SessionDetailDTO(
            session=SessionSummaryDTO(
                session_id=session_id,
                title="In-Memory Session",
                summary=ctx.summary,
                turn_count=len(turns),
            ),
            turns=turns,
            active_facts=[fact_to_dto(f) for f in ctx.active_facts],
        )

    async def get_session_detail(self, session_id: str) -> Optional[SessionDetailDTO]:
        async with self._lock:
            return await asyncio.to_thread(self._get_session_detail_sync, session_id)

    def _rename_session_sync(
        self, session_id: str, title: str
    ) -> Optional[SessionSummaryDTO]:
        clean_title = " ".join(title.strip().split())[:120]
        if not clean_title:
            return None
        memory = self.engine.memory
        if self._has_memory_manager():
            if hasattr(memory, "rename_session"):
                meta = memory.rename_session(session_id, clean_title)  # type: ignore[attr-defined]
                return session_meta_to_dto(meta) if meta is not None else None
            store = getattr(memory, "store", None)
            if store is not None:
                meta = store.rename_session(session_id, clean_title)
                return session_meta_to_dto(meta) if meta is not None else None
        if self._fallback_session_id and session_id == self._fallback_session_id:
            now = datetime.now(timezone.utc).isoformat()
            return SessionSummaryDTO(
                session_id=session_id,
                title=clean_title,
                summary="",
                turn_count=len(memory.get_messages()),
                created_at=now,
                updated_at=now,
            )
        return None

    async def rename_session(
        self, session_id: str, title: str
    ) -> Optional[SessionSummaryDTO]:
        async with self._lock:
            return await asyncio.to_thread(self._rename_session_sync, session_id, title)

    def _clear_session_sync(self, session_id: str) -> Optional[SessionSummaryDTO]:
        memory = self.engine.memory
        if not self._has_memory_manager():
            if not self._fallback_session_id or session_id != self._fallback_session_id:
                return None
            if hasattr(memory, "clear"):
                memory.clear()  # type: ignore[attr-defined]
            return SessionSummaryDTO(
                session_id=session_id,
                title="New Session",
                summary="",
                turn_count=0,
            )

        store = getattr(memory, "store", None)
        if store is not None:
            existing = store.get_session(session_id)
            if existing is None:
                return None
            prior_title = existing.title
            memory.clear(session_id=session_id)  # type: ignore[attr-defined]
            recreated = store.create_session(session_id=session_id, title=prior_title)
            return session_meta_to_dto(recreated)

        if getattr(memory, "session_id", None) != session_id:
            return None
        memory.clear(session_id=session_id)  # type: ignore[attr-defined]
        return SessionSummaryDTO(
            session_id=session_id,
            title="In-Memory Session",
            summary="",
            turn_count=0,
        )

    async def clear_session(self, session_id: str) -> Optional[SessionSummaryDTO]:
        async with self._lock:
            return await asyncio.to_thread(self._clear_session_sync, session_id)

    def _delete_session_sync(self, session_id: str) -> bool:
        memory = self.engine.memory
        if not self._has_memory_manager():
            if self._fallback_session_id and session_id == self._fallback_session_id:
                if hasattr(memory, "clear"):
                    memory.clear()  # type: ignore[attr-defined]
                self._fallback_session_id = None
                return True
            return False

        store = getattr(memory, "store", None)
        if store is not None:
            existing = store.get_session(session_id)
            if existing is None:
                return False
            was_active = getattr(memory, "session_id", None) == session_id
            memory.clear(session_id=session_id)  # type: ignore[attr-defined]
            if was_active:
                memory.session_id = str(uuid.uuid4())  # type: ignore[attr-defined]
            return True

        if getattr(memory, "session_id", None) != session_id:
            return False
        memory.clear(session_id=session_id)  # type: ignore[attr-defined]
        return True

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._delete_session_sync, session_id)


def get_rag_service(request: Request) -> RAGService:
    """FastAPI dependency returning the app-scoped RAGService instance."""
    return request.app.state.rag_service
