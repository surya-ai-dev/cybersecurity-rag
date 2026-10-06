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

    def __getitem__(self, key: str) -> Any:
        """Allow subscript access for backwards compatibility."""
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow subscript assignment for backwards compatibility."""
        setattr(self, key, value)

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

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Message":
        """Instantiate Message from a user-assistant dictionary."""
        return cls(
            user=str(data.get("user", "")),
            assistant=str(data.get("assistant", "")),
        )

    def to_dict(self) -> Dict[str, str]:
        """Convert Message to dictionary representation."""
        return {
            "user": self.user,
            "assistant": self.assistant,
        }

    def __getitem__(self, key: str) -> str:
        """Allow subscript access for backwards compatibility with dictionary format."""
        if key == "user":
            return self.user
        elif key == "assistant":
            return self.assistant
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dict-style get access for backwards compatibility."""
        if key == "user":
            return self.user
        elif key == "assistant":
            return self.assistant
        return default


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
