"""Reciprocal Rank Fusion (RRF) for combining multiple ranked retrieval result lists."""

from typing import Any, Dict, List, Optional, Sequence, Union

from app.core.config import settings
from app.core.models import ChunkMetadata, RetrievedChunk

# Default RRF constant
DEFAULT_RRF_K = 60
DEFAULT_TOP_K = 20


def get_chunk_id(result: Union[RetrievedChunk, Dict[str, Any]]) -> str:
    """Extract the chunk ID from a retrieval result object or dictionary."""
    if isinstance(result, RetrievedChunk):
        return result.chunk_id

    if isinstance(result, dict):
        for key in ("chunk_id", "id", "document_id"):
            val = result.get(key)
            if val is not None:
                return str(val)

    raise ValueError(f"Could not find chunk ID in retrieval result: {result}")


class RRFFusion:
    """Pure computational component that combines ranked retrieval lists using RRF."""

    def __init__(self, k: Optional[int] = None) -> None:
        """Initialize RRF Fusion with constant k.

        Args:
            k: RRF smoothing constant (default: settings.rrf_k or 60).
        """
        self.k: int = k if k is not None else getattr(settings, "rrf_k", DEFAULT_RRF_K)

    def fuse(
        self,
        ranked_lists: Sequence[Sequence[Union[RetrievedChunk, Dict[str, Any]]]],
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Combine multiple ranked candidate lists into a single ranked list using RRF.

        Formula for each item:
            RRF_score(d) = sum_{list in ranked_lists} (1.0 / (k + rank(d, list)))

        Args:
            ranked_lists: Sequence of ranked result lists (e.g. [dense_results, bm25_results]).
            top_k: Maximum number of fused results to return.

        Returns:
            List of fused RetrievedChunk instances sorted by descending RRF score.
        """
        if not ranked_lists:
            return []

        limit = top_k if top_k is not None else DEFAULT_TOP_K

        scores: Dict[str, float] = {}
        documents: Dict[str, Union[RetrievedChunk, Dict[str, Any]]] = {}

        for results in ranked_lists:
            for rank, result in enumerate(results, start=1):
                chunk_id = get_chunk_id(result)
                rrf_score = 1.0 / (self.k + rank)

                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score

                if chunk_id not in documents:
                    documents[chunk_id] = result

        ranked_chunk_ids = sorted(
            scores.keys(),
            key=lambda cid: scores[cid],
            reverse=True,
        )

        fused_results: List[RetrievedChunk] = []

        for rank, chunk_id in enumerate(ranked_chunk_ids[:limit], start=1):
            original = documents[chunk_id]
            final_score = scores[chunk_id]

            if isinstance(original, RetrievedChunk):
                chunk = original.copy()
                chunk.score = final_score
                chunk.rrf_score = final_score
                chunk["rrf_rank"] = rank
                fused_results.append(chunk)
            elif isinstance(original, dict):
                raw_meta = original.get("metadata", {})
                metadata = (
                    raw_meta
                    if isinstance(raw_meta, ChunkMetadata)
                    else ChunkMetadata.from_dict(raw_meta if isinstance(raw_meta, dict) else {})
                )

                chunk = RetrievedChunk(
                    chunk_id=str(chunk_id),
                    text=str(original.get("text", "")),
                    score=final_score,
                    rrf_score=final_score,
                    dense_score=original.get("dense_score"),
                    bm25_score=original.get("bm25_score"),
                    metadata=metadata,
                )
                chunk["rrf_rank"] = rank
                fused_results.append(chunk)

        return fused_results


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Union[RetrievedChunk, Dict[str, Any]]]],
    top_k: int = DEFAULT_TOP_K,
    k: int = DEFAULT_RRF_K,
) -> List[RetrievedChunk]:
    """Functional interface for Reciprocal Rank Fusion, preserving backwards compatibility."""
    fusion = RRFFusion(k=k)
    return fusion.fuse(ranked_lists, top_k=top_k)


def print_fusion_results(
    results: List[Union[RetrievedChunk, Dict[str, Any]]],
    title: str = "RRF RESULTS",
) -> None:
    """Pretty-print fused retrieval results."""
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)

    if not results:
        print("No results.")
        return

    for result in results:
        chunk_id = get_chunk_id(result)
        rank = result.get("rrf_rank", "?")
        score = result.get("rrf_score", 0.0)
        print(f"{rank:>2}. {chunk_id:<40} RRF={score:.6f}")


def main():
    """Demo test for pure RRF fusion."""
    print("=" * 70)
    print("RRF FUSION TEST")
    print("=" * 70)

    dense_results = [
        {"chunk_id": "A", "text": "Dense A"},
        {"chunk_id": "B", "text": "Dense B"},
        {"chunk_id": "C", "text": "Dense C"},
    ]

    bm25_results = [
        {"chunk_id": "C", "text": "BM25 C"},
        {"chunk_id": "A", "text": "BM25 A"},
        {"chunk_id": "D", "text": "BM25 D"},
    ]

    fusion = RRFFusion(k=60)
    fused = fusion.fuse([dense_results, bm25_results], top_k=5)
    print_fusion_results(fused, title="RRF FUSED RESULTS")


if __name__ == "__main__":
    main()
