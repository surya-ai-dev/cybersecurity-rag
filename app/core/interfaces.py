"""Core domain protocols and interfaces for the Cybersecurity RAG system."""

from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Protocol,
    Union,
    runtime_checkable,
)

from app.core.models import Message, RetrievedChunk


@runtime_checkable
class BaseRetriever(Protocol):
    """Protocol for document retrieval strategies (Dense, BM25, Hybrid)."""

    def retrieve(
        self,
        query: str,
        top_k: int = 20,
    ) -> List[Union[RetrievedChunk, Dict[str, Any]]]:
        """Retrieve candidate documents for a given query."""
        ...


@runtime_checkable
class BaseReranker(Protocol):
    """Protocol for reranking candidate documents."""

    def rerank(
        self,
        query: str,
        documents: List[Union[RetrievedChunk, Dict[str, Any]]],
        top_n: int = 5,
    ) -> List[Union[RetrievedChunk, Dict[str, Any]]]:
        """Rerank candidate documents against the query."""
        ...


@runtime_checkable
class BaseLLMProvider(Protocol):
    """Protocol for LLM provider implementations (Groq, Ollama, OpenAI, etc.)."""

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> str:
        """Generate a complete text response for a given prompt."""
        ...

    def stream(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> Iterator[str]:
        """Stream response text chunks for a given prompt."""
        ...


@runtime_checkable
class BaseConversationMemory(Protocol):
    """Protocol for managing multi-turn conversational history."""

    def add_message(
        self,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Record a single interaction turn."""
        ...

    def get_messages(
        self,
    ) -> List[Union[Message, Dict[str, str]]]:
        """Retrieve the recorded conversation history."""
        ...


@runtime_checkable
class BaseVectorStore(Protocol):
    """Minimal protocol for vector storage search."""

    def search(
        self,
        query_vector: List[float],
        limit: int = 20,
    ) -> List[Union[RetrievedChunk, Dict[str, Any]]]:
        """Perform vector similarity search against stored embeddings."""
        ...
