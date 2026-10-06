"""Hybrid retriever orchestrating Dense retrieval, BM25 retrieval, and RRF fusion."""

from typing import List, Optional

from app.core.config import settings
from app.core.interfaces import BaseRetriever
from app.core.models import RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.rrf import RRFFusion


class HybridRetriever(BaseRetriever):
    """Orchestrates hybrid retrieval combining dense vector search and keyword BM25 via RRF.

    Conforms to BaseRetriever and accepts injected component strategies.
    """

    def __init__(
        self,
        dense_retriever: Optional[BaseRetriever] = None,
        bm25_retriever: Optional[BaseRetriever] = None,
        fusion: Optional[RRFFusion] = None,
        dense_top_k: Optional[int] = None,
        bm25_top_k: Optional[int] = None,
        default_top_k: Optional[int] = None,
    ) -> None:
        """Initialize the HybridRetriever.

        Args:
            dense_retriever: Component implementing BaseRetriever for dense semantic search.
            bm25_retriever: Component implementing BaseRetriever for BM25 keyword search.
            fusion: Component implementing RRFFusion for score combination.
            dense_top_k: Candidate limit for dense retrieval (default: settings.dense_top_k).
            bm25_top_k: Candidate limit for BM25 retrieval (default: settings.bm25_top_k).
            default_top_k: Default final fused result limit.
        """
        self._dense_retriever = dense_retriever
        self._bm25_retriever = bm25_retriever
        self._fusion = fusion

        self.dense_top_k = dense_top_k or settings.dense_top_k
        self.bm25_top_k = bm25_top_k or settings.bm25_top_k
        self.default_top_k = default_top_k or 20

    @property
    def dense_retriever(self) -> BaseRetriever:
        """Lazily initialize default DenseRetriever if not provided."""
        if self._dense_retriever is None:
            self._dense_retriever = DenseRetriever()
        return self._dense_retriever

    @property
    def bm25_retriever(self) -> BaseRetriever:
        """Lazily initialize default BM25Retriever if not provided."""
        if self._bm25_retriever is None:
            self._bm25_retriever = BM25Retriever()
        return self._bm25_retriever

    @property
    def fusion(self) -> RRFFusion:
        """Lazily initialize default RRFFusion if not provided."""
        if self._fusion is None:
            self._fusion = RRFFusion()
        return self._fusion

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Execute hybrid search by querying dense and BM25 retrievers and fusing with RRF.

        Args:
            query: User search query or rewritten question.
            top_k: Number of fused results to return.

        Returns:
            List of fused RetrievedChunk instances.
        """
        if not query or not query.strip():
            return []

        limit = top_k if top_k is not None else self.default_top_k

        print("\nDense retrieval...")
        dense_results = self.dense_retriever.retrieve(
            query,
            top_k=self.dense_top_k,
        )
        print(f"Dense results: {len(dense_results)}")

        print("\nBM25 retrieval...")
        bm25_results = self.bm25_retriever.retrieve(
            query,
            top_k=self.bm25_top_k,
        )
        print(f"BM25 results: {len(bm25_results)}")

        print("\nRRF fusion...")
        fused_results = self.fusion.fuse(
            [dense_results, bm25_results],
            top_k=limit,
        )
        print(f"Final RRF results: {len(fused_results)}")

        return fused_results

    def close(self) -> None:
        """Close underlying retriever resources if open."""
        if self._dense_retriever is not None and hasattr(self._dense_retriever, "close"):
            self._dense_retriever.close()
        if self._bm25_retriever is not None and hasattr(self._bm25_retriever, "close"):
            self._bm25_retriever.close()

    def __enter__(self) -> "HybridRetriever":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def main():
    """CLI test for HybridRetriever."""
    print("=" * 70)
    print("HYBRID RETRIEVER TEST")
    print("=" * 70)

    with HybridRetriever() as retriever:
        question = input("\nEnter cybersecurity question: ").strip()
        if not question:
            print("Question cannot be empty.")
            return

        results = retriever.retrieve(question, top_k=5)
        for rank, chunk in enumerate(results, start=1):
            print(f"\n[{rank}] RRF: {chunk.rrf_score:.6f} | Chunk ID: {chunk.chunk_id}")
            print(f"    Document: {chunk.metadata.document_id} | Section: {chunk.metadata.section}")
            print(f"    Text: {chunk.text[:150]}...")


if __name__ == "__main__":
    main()
