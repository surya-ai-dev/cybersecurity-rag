"""Compatibility layer for the RAG pipeline.

Delegates execution to the modularized RAGEngine orchestrator.
"""

from typing import Any, List, Optional, Tuple

from app.core.interfaces import BaseConversationMemory
from app.core.models import RetrievedChunk
from app.pipeline.engine import RAGEngine

# Module-level default RAGEngine instance
_default_engine: Optional[RAGEngine] = None


def get_default_engine() -> RAGEngine:
    """Return the shared default RAGEngine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = RAGEngine()
    return _default_engine


# Expose default memory for backwards compatibility
def _get_default_memory() -> BaseConversationMemory:
    return get_default_engine().memory


conversation_memory: BaseConversationMemory = _get_default_memory()
conversation_history: BaseConversationMemory = conversation_memory
MAX_HISTORY_MESSAGES = 6


def run_rag(question: str) -> Tuple[str, List[RetrievedChunk]]:
    """Execute RAG pipeline on a question, returning the answer string and sources."""
    engine = get_default_engine()
    response = engine.query(question, stream=True)
    return response.answer, response.sources


def close_retriever() -> None:
    """Close underlying engine resources cleanly."""
    global _default_engine
    if _default_engine is not None:
        _default_engine.close()
        _default_engine = None


def main(memory: Optional[BaseConversationMemory] = None) -> None:
    """Interactive CLI entry point for the Cybersecurity RAG system."""
    engine = RAGEngine(memory=memory) if memory is not None else get_default_engine()

    print("=" * 70)
    print("CYBERSECURITY RAG SYSTEM")
    print("=" * 70)

    while True:
        question = input(
            "\nEnter cybersecurity question (type 'exit' to quit): "
        )

        if question.lower() == "exit":
            break

        if not question.strip():
            print("❌ Question cannot be empty.")
            continue

        response = engine.query(question, stream=True)

        print(
            f"\nDEBUG: Stored conversations = "
            f"{len(engine.memory.get_messages())}"
        )

        print("\n" + "=" * 70)
        print("SOURCES")
        print("=" * 70)

        for index, result in enumerate(response.sources, start=1):
            metadata = result.metadata
            doc_id = metadata.document_id if hasattr(metadata, "document_id") else metadata.get("document_id", "Unknown")
            source_file = metadata.source_file if hasattr(metadata, "source_file") else metadata.get("source_file", "Unknown")
            section = metadata.section if hasattr(metadata, "section") else metadata.get("section", "Unknown")
            score = result.reranker_score if result.reranker_score is not None else result.get("reranker_score", 0.0)

            print(f"[{index}] {doc_id} | {source_file}")
            print(f"    Section: {section}")
            print(f"    Reranker score: {score:.4f}")

    engine.close()


if __name__ == "__main__":
    main()