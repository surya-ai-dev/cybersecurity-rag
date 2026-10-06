"""Backward-compatible functional interface for retrieval.

Delegates to modularized HybridRetriever, DenseRetriever, and BM25Retriever.
"""

from typing import List, Optional

from app.core.models import RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.rrf import reciprocal_rank_fusion

# Module-level default retriever instance (lazy-initialized upon first call)
_default_hybrid_retriever: Optional[HybridRetriever] = None


def get_default_retriever() -> HybridRetriever:
    """Return the shared default HybridRetriever instance."""
    global _default_hybrid_retriever
    if _default_hybrid_retriever is None:
        _default_hybrid_retriever = HybridRetriever()
    return _default_hybrid_retriever


def dense_retrieve(
    question: str,
    top_k: int = 20,
) -> List[RetrievedChunk]:
    """Execute dense semantic search using the default DenseRetriever."""
    return get_default_retriever().dense_retriever.retrieve(question, top_k=top_k)


def retrieve(
    question: str,
    top_k: int = 20,
) -> List[RetrievedChunk]:
    """Execute hybrid retrieval (dense + BM25 + RRF)."""
    return get_default_retriever().retrieve(question, top_k=top_k)


def close_retriever() -> None:
    """Close shared retriever connections and release database handles."""
    global _default_hybrid_retriever
    if _default_hybrid_retriever is not None:
        _default_hybrid_retriever.close()
        _default_hybrid_retriever = None


def main():
    """CLI entry point for testing backward-compatible retrieve()."""
    question = input("\nEnter cybersecurity question: ").strip()
    if not question:
        print("Question cannot be empty.")
        return

    results = retrieve(question, top_k=5)
    for rank, chunk in enumerate(results, start=1):
        print(f"\n[{rank}] Score: {chunk.score:.6f} | Chunk ID: {chunk.chunk_id}")
        print(f"    Text: {chunk.text[:150]}...")

    close_retriever()


if __name__ == "__main__":
    main()