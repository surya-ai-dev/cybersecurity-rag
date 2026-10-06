"""Cross-Encoder reranker for the Cybersecurity RAG system.

Reranks candidate chunks retrieved from hybrid search using a pretrained
CrossEncoder model.
"""

from typing import Any, Dict, List, Optional, Sequence, Union

from app.core.config import settings
from app.core.interfaces import BaseReranker
from app.core.models import ChunkMetadata, RetrievedChunk

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_TOP_N = 5


class CrossEncoderReranker(BaseReranker):
    """Reranker using a CrossEncoder transformer model conforming to BaseReranker."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        default_top_n: Optional[int] = None,
        lazy_load: bool = True,
    ) -> None:
        """Initialize CrossEncoderReranker.

        Args:
            model_name: HuggingFace model name or local path (default: settings.reranker_model).
            default_top_n: Default number of top reranked chunks to return.
            lazy_load: If True, defer model weights loading until first rerank call.
        """
        self.model_name: str = model_name or getattr(settings, "reranker_model", DEFAULT_RERANKER_MODEL)
        self.default_top_n: int = default_top_n or getattr(settings, "final_top_n", DEFAULT_TOP_N)
        self._model = None

        if not lazy_load:
            self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Lazily load the CrossEncoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                local_files_only=True,
            )

    @property
    def model(self):
        """Access the underlying CrossEncoder model."""
        self._ensure_initialized()
        return self._model

    def rerank(
        self,
        query: str,
        documents: Sequence[Union[RetrievedChunk, Dict[str, Any]]],
        top_n: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Rerank candidate chunks against the query using the Cross-Encoder.

        Args:
            query: The user query or standalone question.
            documents: Candidate chunks from prior retrieval/fusion.
            top_n: Number of top reranked chunks to return. Defaults to self.default_top_n.

        Returns:
            List of RetrievedChunk instances sorted by descending reranker score.
        """
        if not documents:
            return []

        limit = top_n if top_n is not None else self.default_top_n
        self._ensure_initialized()

        print(f"\nReranking {len(documents)} documents...")

        # Extract query-document text pairs
        pairs = []
        doc_objects: List[RetrievedChunk] = []

        for doc in documents:
            if isinstance(doc, RetrievedChunk):
                chunk = doc.copy()
            elif isinstance(doc, dict):
                raw_meta = doc.get("metadata", {})
                metadata = (
                    raw_meta
                    if isinstance(raw_meta, ChunkMetadata)
                    else ChunkMetadata.from_dict(raw_meta if isinstance(raw_meta, dict) else {})
                )
                chunk = RetrievedChunk(
                    chunk_id=str(doc.get("chunk_id", "Unknown")),
                    text=str(doc.get("text", "")),
                    score=float(doc.get("score", 0.0)),
                    dense_score=doc.get("dense_score"),
                    bm25_score=doc.get("bm25_score"),
                    rrf_score=doc.get("rrf_score"),
                    metadata=metadata,
                )
            else:
                chunk = RetrievedChunk(chunk_id=str(doc), text=str(doc))

            pairs.append((query, chunk.text))
            doc_objects.append(chunk)

        # Predict relevance scores
        scores = self._model.predict(
            pairs,
            show_progress_bar=False,
        )

        for chunk, score in zip(doc_objects, scores):
            float_score = float(score)
            chunk.reranker_score = float_score
            chunk["reranker_score"] = float_score

        # Sort descending by reranker score
        doc_objects.sort(
            key=lambda c: c.reranker_score if c.reranker_score is not None else float("-inf"),
            reverse=True,
        )

        return doc_objects[:limit]

    def close(self) -> None:
        """Release reranker model resources if needed."""
        self._model = None

    def __enter__(self) -> "CrossEncoderReranker":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# Module-level default reranker instance (lazy-initialized upon first call)
_default_reranker: Optional[CrossEncoderReranker] = None


def get_default_reranker() -> CrossEncoderReranker:
    """Return the shared default CrossEncoderReranker instance."""
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = CrossEncoderReranker()
    return _default_reranker


def rerank_documents(
    question: str,
    documents: Sequence[Union[RetrievedChunk, Dict[str, Any]]],
    top_n: int = DEFAULT_TOP_N,
) -> List[RetrievedChunk]:
    """Functional interface for reranking candidate documents, preserving backwards compatibility."""
    return get_default_reranker().rerank(
        query=question,
        documents=documents,
        top_n=top_n,
    )


def display_reranked_results(documents: Sequence[Union[RetrievedChunk, Dict[str, Any]]]) -> None:
    """Display reranked documents with scores and metadata."""
    print("\n" + "=" * 70)
    print("RERANKED RESULTS")
    print("=" * 70)

    for rank, doc in enumerate(documents, start=1):
        if isinstance(doc, RetrievedChunk):
            doc_id = doc.metadata.document_id
            source = doc.metadata.source_file
            section = doc.metadata.section
            score = doc.reranker_score or 0.0
            text = doc.text
            chunk_id = doc.chunk_id
        else:
            meta = doc.get("metadata", {})
            doc_id = meta.get("document_id", "Unknown")
            source = meta.get("source_file", "Unknown")
            section = meta.get("section", "Unknown")
            score = doc.get("reranker_score", 0.0)
            text = doc.get("text", "")
            chunk_id = doc.get("chunk_id", "Unknown")

        print(f"\nRank {rank}")
        print(f"Document       : {doc_id}")
        print(f"Source         : {source}")
        print(f"Section        : {section}")
        print(f"Reranker Score : {score:.4f}")
        print(f"Chunk ID       : {chunk_id}")
        print(f"Content        : {text[:200]}...")


def main():
    """CLI test for CrossEncoderReranker."""
    from app.retrieval.retriever import retrieve

    question = input("\nEnter cybersecurity question: ").strip()
    if not question:
        print("Question cannot be empty.")
        return

    print("\nRetrieving candidates...")
    candidates = retrieve(question, top_k=20)

    reranker = CrossEncoderReranker()
    reranked = reranker.rerank(question, candidates, top_n=5)
    display_reranked_results(reranked)


if __name__ == "__main__":
    main()