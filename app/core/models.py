"""Domain data models for the Cybersecurity RAG system."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChunkMetadata:
    """Metadata associated with an extracted and indexed text chunk."""

    document_id: str = "Unknown"
    category: str = "Unknown"
    source_file: str = "Unknown"
    section: str = "Unknown"
    token_count: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ChunkMetadata":
        """Instantiate ChunkMetadata from a dictionary."""
        if not data:
            return cls()

        known_keys = {"document_id", "category", "source_file", "section", "token_count"}
        known_kwargs = {k: data[k] for k in known_keys if k in data}
        extra_kwargs = {k: v for k, v in data.items() if k not in known_keys}

        return cls(**known_kwargs, extra=extra_kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ChunkMetadata to a dictionary representation."""
        result = {
            "document_id": self.document_id,
            "category": self.category,
            "source_file": self.source_file,
            "section": self.section,
            "token_count": self.token_count,
        }
        if self.extra:
            result.update(self.extra)
        return result

    def __getitem__(self, key: str) -> Any:
        """Allow subscript access for backwards compatibility."""
        if hasattr(self, key) and key != "extra":
            return getattr(self, key)
        if key in self.extra:
            return self.extra[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dict-style get access for backwards compatibility."""
        if hasattr(self, key) and key != "extra":
            val = getattr(self, key)
            return val if val is not None else default
        return self.extra.get(key, default)


@dataclass
class RetrievedChunk:
    """Represents a document chunk retrieved from vector, keyword, or hybrid search."""

    chunk_id: str
    text: str
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)
    score: float = 0.0
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: Optional[float] = None
    reranker_score: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievedChunk":
        """Instantiate RetrievedChunk from an existing dictionary structure."""
        meta_data = data.get("metadata")
        if isinstance(meta_data, dict):
            metadata = ChunkMetadata.from_dict(meta_data)
        elif isinstance(meta_data, ChunkMetadata):
            metadata = meta_data
        else:
            metadata = ChunkMetadata()

        return cls(
            chunk_id=str(data.get("chunk_id", "Unknown")),
            text=str(data.get("text", "")),
            metadata=metadata,
            score=float(data.get("score", 0.0)),
            dense_score=data.get("dense_score"),
            bm25_score=data.get("bm25_score"),
            rrf_score=data.get("rrf_score"),
            reranker_score=data.get("reranker_score"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert RetrievedChunk to a dictionary matching existing pipeline expectations."""
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "metadata": self.metadata.to_dict(),
            "score": self.score,
            "dense_score": self.dense_score,
            "bm25_score": self.bm25_score,
            "rrf_score": self.rrf_score,
            "reranker_score": self.reranker_score,
        }

    def __getitem__(self, key: Any) -> Any:
        """Allow subscript access for backwards compatibility."""
        if isinstance(key, str) and hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow subscript assignment for backwards compatibility."""
        setattr(self, key, value)

    def __contains__(self, key: Any) -> bool:
        """Allow 'in' membership check for backwards compatibility."""
        return isinstance(key, str) and hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dict-style get access for backwards compatibility."""
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        return default

    def copy(self) -> "RetrievedChunk":
        """Return a shallow copy of the RetrievedChunk."""
        return RetrievedChunk(
            chunk_id=self.chunk_id,
            text=self.text,
            metadata=self.metadata,
            score=self.score,
            dense_score=self.dense_score,
            bm25_score=self.bm25_score,
            rrf_score=self.rrf_score,
            reranker_score=self.reranker_score,
        )


@dataclass
class Message:
    """Represents a single conversational turn between user and assistant."""

    user: str
    assistant: str
    timestamp: Optional[str] = None
    standalone_question: Optional[str] = None
    source_chunk_ids: List[str] = field(default_factory=list)
    turn_index: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Instantiate Message from a user-assistant dictionary."""
        raw_chunks = data.get("source_chunk_ids")
        source_chunk_ids = (
            [str(cid) for cid in raw_chunks]
            if isinstance(raw_chunks, list)
            else []
        )
        raw_turn = data.get("turn_index")
        turn_index = int(raw_turn) if raw_turn is not None else None
        raw_ts = data.get("timestamp")
        raw_sq = data.get("standalone_question")

        return cls(
            user=str(data.get("user", "")),
            assistant=str(data.get("assistant", "")),
            timestamp=str(raw_ts) if raw_ts is not None else None,
            standalone_question=str(raw_sq) if raw_sq is not None else None,
            source_chunk_ids=source_chunk_ids,
            turn_index=turn_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Message to dictionary representation."""
        result: Dict[str, Any] = {
            "user": self.user,
            "assistant": self.assistant,
        }
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp
        if self.standalone_question is not None:
            result["standalone_question"] = self.standalone_question
        if self.source_chunk_ids:
            result["source_chunk_ids"] = list(self.source_chunk_ids)
        if self.turn_index is not None:
            result["turn_index"] = self.turn_index
        return result

    def __getitem__(self, key: str) -> Any:
        """Allow subscript access for backwards compatibility with dictionary format."""
        if key in {"user", "assistant", "timestamp", "standalone_question", "source_chunk_ids", "turn_index"}:
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dict-style get access for backwards compatibility."""
        if key in {"user", "assistant", "timestamp", "standalone_question", "source_chunk_ids", "turn_index"}:
            val = getattr(self, key)
            return val if val is not None else default
        return default


@dataclass
class SessionMetadata:
    """Metadata describing a persisted multi-turn conversation session."""

    session_id: str
    title: str = "New Session"
    summary: str = ""
    turn_count: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class MemoryFact:
    """Durable domain scope, constraint, or entity fact tracked across turns."""

    fact_id: str
    session_id: str
    category: str
    key: str
    value: str
    source_turn: Optional[int] = None
    confidence: float = 1.0
    updated_at: str = ""


@dataclass
class MemoryContext:
    """Aggregated three-tier memory context supplied to query disambiguation."""

    session_id: Optional[str] = None
    recent_messages: List[Message] = field(default_factory=list)
    summary: str = ""
    active_facts: List[MemoryFact] = field(default_factory=list)
    total_tokens: int = 0

    @property
    def has_context(self) -> bool:
        """Return True when any tier contains usable conversational context."""
        return bool(self.recent_messages or self.summary.strip() or self.active_facts)


@dataclass
class RAGResponse:
    """Represents the complete output of an end-to-end RAG query."""

    question: str
    standalone_question: str
    answer: str
    sources: List[RetrievedChunk] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert RAGResponse to a dictionary representation."""
        return {
            "question": self.question,
            "standalone_question": self.standalone_question,
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
        }
