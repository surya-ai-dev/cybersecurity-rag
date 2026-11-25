"""Unified 3-tier MemoryManager coordinating short-term, persistent, summary, and long-term memory."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Union
import uuid

from app.conversation.long_term_memory import LongTermMemory
from app.conversation.short_term_memory import ShortTermMemory, TokenCounter
from app.conversation.storage import SQLiteMemoryStore
from app.conversation.summarizer import ConversationSummarizer
from app.core.config import settings
from app.core.interfaces import BaseLLMProvider
from app.core.models import MemoryContext, MemoryFact, Message, SessionMetadata


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryManager:
    """Drop-in memory orchestrator conforming to BaseConversationMemory and BaseMemoryManager."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        store: Optional[SQLiteMemoryStore] = None,
        short_term: Optional[ShortTermMemory] = None,
        summarizer: Optional[ConversationSummarizer] = None,
        long_term: Optional[LongTermMemory] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
        db_path: Optional[Union[str, Path]] = None,
        enable_persistence: Optional[bool] = None,
        enable_summarization: Optional[bool] = None,
        enable_long_term: Optional[bool] = None,
        summarize_after_turns: Optional[int] = None,
        long_term_top_k: Optional[int] = None,
    ) -> None:
        self.enable_persistence: bool = (
            enable_persistence
            if enable_persistence is not None
            else (
                True
                if store is not None
                else getattr(settings, "enable_persistent_memory", False)
            )
        )
        self.enable_summarization: bool = (
            enable_summarization
            if enable_summarization is not None
            else getattr(settings, "enable_memory_summarization", False)
        )
        self.enable_long_term: bool = (
            enable_long_term
            if enable_long_term is not None
            else getattr(settings, "enable_long_term_memory", False)
        )
        raw_sum_turns = (
            summarize_after_turns
            if summarize_after_turns is not None
            else getattr(settings, "memory_summarize_after_turns", 6)
        )
        self.summarize_after_turns: int = max(1, int(raw_sum_turns))

        raw_ltm_k = (
            long_term_top_k
            if long_term_top_k is not None
            else getattr(settings, "memory_long_term_top_k", 3)
        )
        self.long_term_top_k: int = max(0, int(raw_ltm_k))

        self.session_id: str = session_id.strip() if session_id and session_id.strip() else str(uuid.uuid4())

        self.short_term: ShortTermMemory = (
            short_term
            if short_term is not None
            else ShortTermMemory(
                max_recent_messages=getattr(settings, "conversation_history_limit", 6),
                max_tokens=getattr(settings, "memory_max_history_tokens", 1500),
            )
        )

        # Pure in-memory mode must never open or create SQLite files on disk.
        self.store: Optional[SQLiteMemoryStore]
        if self.enable_persistence:
            if store is not None:
                self.store = store
            else:
                resolved_db = db_path if db_path is not None else settings.memory_db_path
                self.store = SQLiteMemoryStore(resolved_db)
        else:
            self.store = None

        self.summarizer: ConversationSummarizer = (
            summarizer
            if summarizer is not None
            else ConversationSummarizer(
                llm_provider=llm_provider,
                max_summary_tokens=getattr(settings, "memory_max_summary_tokens", 300),
                token_counter=self.short_term.token_counter,
            )
        )

        self.long_term: LongTermMemory = (
            long_term
            if long_term is not None
            else LongTermMemory(
                store=self.store,
                embed_fn=embed_fn,
            )
        )
        if self.enable_persistence and self.store is not None and self.long_term.store is None:
            self.long_term.store = self.store

        self._summary: str = ""
        self._total_turns: int = 0
        self._pending_evicted: List[Message] = []

        if self.enable_persistence and self.store is not None:
            self._hydrate_from_store(self.session_id)

    def _hydrate_from_store(self, session_id: str) -> None:
        """Load recent turns and existing summary if session_id exists in SQLite."""
        if self.store is None:
            return
        existing = self.store.get_session(session_id)
        if existing is None:
            self._summary = ""
            self._total_turns = 0
            self.short_term.clear()
            return

        self._summary = existing.summary
        self._total_turns = existing.turn_count
        recent = self.store.get_recent_turns(
            session_id,
            limit=max(1, self.short_term.max_recent_messages),
        )
        self.short_term.hydrate(recent)

    def add_message(
        self,
        user_message: Union[str, Message],
        assistant_message: str = "",
        *,
        standalone_question: Optional[str] = None,
        source_chunk_ids: Optional[Sequence[str]] = None,
    ) -> None:
        """Record a turn across short-term, persistent, long-term, and summary tiers."""
        now = _utc_now_iso()
        if isinstance(user_message, Message):
            msg = Message(
                user=user_message.user,
                assistant=user_message.assistant,
                timestamp=user_message.timestamp or now,
                standalone_question=standalone_question
                if standalone_question is not None
                else user_message.standalone_question,
                source_chunk_ids=list(source_chunk_ids)
                if source_chunk_ids is not None
                else list(user_message.source_chunk_ids),
                turn_index=user_message.turn_index,
            )
        else:
            msg = Message(
                user=str(user_message),
                assistant=str(assistant_message),
                timestamp=now,
                standalone_question=standalone_question,
                source_chunk_ids=list(source_chunk_ids) if source_chunk_ids is not None else [],
            )

        if self.enable_persistence and self.store is not None:
            turn_index = self.store.append_turn(self.session_id, msg)
            msg.turn_index = turn_index
            self._total_turns = turn_index
        else:
            self._total_turns += 1
            msg.turn_index = self._total_turns

        evicted = self.short_term.add(msg)
        if evicted:
            self._pending_evicted.extend(evicted)

        if self.enable_long_term:
            self.long_term.record_turn(
                session_id=self.session_id,
                user_message=msg.user,
                assistant_message=msg.assistant,
                source_turn=msg.turn_index,
            )

        if self.enable_summarization:
            self._maybe_summarize(msg.turn_index)

    def _maybe_summarize(self, current_turn_index: int) -> None:
        """Compress turns aged beyond the active short-term window once threshold is crossed."""
        if current_turn_index <= self.summarize_after_turns:
            return

        cutoff_turn = max(0, current_turn_index - len(self.short_term))

        if self.enable_persistence and self.store is not None:
            if cutoff_turn <= 0:
                return
            overflow_turns = self.store.get_unsummarized_turns(
                self.session_id,
                up_to_turn_index=cutoff_turn,
            )
            if not overflow_turns:
                return
            self._summary = self.summarizer.summarize(self._summary, overflow_turns)
            last_idx = overflow_turns[-1].turn_index or cutoff_turn
            self.store.update_summary(
                self.session_id,
                self._summary,
                last_summarized_turn_index=last_idx,
            )
            self._pending_evicted.clear()
        elif self._pending_evicted:
            self._summary = self.summarizer.summarize(self._summary, self._pending_evicted)
            self._pending_evicted.clear()

    def get_messages(self) -> List[Message]:
        """Return token-trimmed recent messages for the active session."""
        return self.short_term.get_messages()

    def get_context(
        self,
        query: str = "",
        session_id: Optional[str] = None,
    ) -> MemoryContext:
        """Assemble short-term turns, rolling summary, and active long-term facts."""
        target_sid = session_id if session_id is not None else self.session_id

        if target_sid == self.session_id:
            recent_messages = self.get_messages()
            summary = self._summary
        elif self.enable_persistence and self.store is not None:
            raw_turns = self.store.get_recent_turns(
                target_sid,
                limit=max(1, self.short_term.max_recent_messages),
            )
            temp_stm = ShortTermMemory(
                max_recent_messages=self.short_term.max_recent_messages,
                max_tokens=self.short_term.max_tokens,
                token_counter=self.short_term.token_counter,
            )
            temp_stm.hydrate(raw_turns)
            recent_messages = temp_stm.get_messages()
            meta = self.store.get_session(target_sid)
            summary = meta.summary if meta is not None else ""
        else:
            recent_messages = []
            summary = ""

        active_facts: List[MemoryFact] = []
        if self.enable_long_term and self.long_term_top_k > 0:
            active_facts = self.long_term.recall(
                query=query,
                session_id=target_sid,
                top_k=self.long_term_top_k,
            )

        tc: TokenCounter = self.short_term.token_counter
        total_tokens = (
            self.short_term.total_tokens(recent_messages)
            + tc.count_text(summary)
            + sum(tc.count_text(f"{f.key}: {f.value}") for f in active_facts)
        )

        return MemoryContext(
            session_id=target_sid,
            recent_messages=recent_messages,
            summary=summary,
            active_facts=active_facts,
            total_tokens=total_tokens,
        )

    def new_session(self, title: Optional[str] = None) -> SessionMetadata:
        """Start and activate a brand-new conversation session."""
        self.session_id = str(uuid.uuid4())
        self.short_term.clear()
        self._summary = ""
        self._total_turns = 0
        self._pending_evicted.clear()

        if self.enable_persistence and self.store is not None:
            return self.store.create_session(session_id=self.session_id, title=title)

        now = _utc_now_iso()
        return SessionMetadata(
            session_id=self.session_id,
            title=title or "New Session",
            summary="",
            turn_count=0,
            created_at=now,
            updated_at=now,
        )

    def switch_session(self, session_id: str) -> SessionMetadata:
        """Switch active session and hydrate state if present in persistent store."""
        self.session_id = session_id
        self._pending_evicted.clear()

        if self.enable_persistence and self.store is not None:
            meta = self.store.get_session(session_id)
            if meta is None:
                meta = self.store.create_session(session_id=session_id)
            self._hydrate_from_store(session_id)
            return meta

        self.short_term.clear()
        self._summary = ""
        self._total_turns = 0
        now = _utc_now_iso()
        return SessionMetadata(
            session_id=session_id,
            title="In-Memory Session",
            summary="",
            turn_count=0,
            created_at=now,
            updated_at=now,
        )

    def list_sessions(self, limit: int = 20) -> List[SessionMetadata]:
        """List saved sessions (or current in-memory session when persistence is disabled)."""
        if self.enable_persistence and self.store is not None:
            return self.store.list_sessions(limit=limit)

        return [
            SessionMetadata(
                session_id=self.session_id,
                title="In-Memory Session",
                summary=self._summary,
                turn_count=self._total_turns,
            )
        ]

    def rename_session(self, session_id: str, title: str) -> Optional[SessionMetadata]:
        """Rename an existing session and return updated metadata if found."""
        clean_title = " ".join(title.strip().split())
        if not clean_title:
            return None
        if self.enable_persistence and self.store is not None:
            return self.store.rename_session(session_id, clean_title)
        if session_id == self.session_id:
            now = _utc_now_iso()
            return SessionMetadata(
                session_id=self.session_id,
                title=clean_title,
                summary=self._summary,
                turn_count=self._total_turns,
                created_at=now,
                updated_at=now,
            )
        return None

    def clear(self, session_id: Optional[str] = None) -> None:
        """Clear working buffer and persisted records for the target or active session."""
        target_sid = session_id if session_id is not None else self.session_id
        if target_sid == self.session_id:
            self.short_term.clear()
            self._summary = ""
            self._total_turns = 0
            self._pending_evicted.clear()

        if self.enable_persistence and self.store is not None:
            self.store.delete_session(target_sid)

    def close(self) -> None:
        """Cleanly close persistent store resources."""
        if self.store is not None:
            self.store.close()

    def __enter__(self) -> "MemoryManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
