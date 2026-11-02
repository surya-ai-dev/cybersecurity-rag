"""Reciprocal Rank Fusion (RRF) for combining multiple ranked retrieval result lists."""

from typing import Any, Dict, List, Optional, Sequence, Union

from app.core.config import settings
from app.core.models import ChunkMetadata, RetrievedChunk

# Default RRF constant
DEFAULT_RRF_K = 60
DEFAULT_TOP_K = 20


def get_chunk_id(result: Union[RetrievedChunk, Dict[str, Any], Any]) -> str:
    """Extract the chunk ID from a retrieval result object, dictionary, or Qdrant point."""
    if isinstance(result, RetrievedChunk):
        return result.chunk_id

    if isinstance(result, dict):
        for key in ("chunk_id", "id", "document_id"):
            val = result.get(key)
            if val is not None:
                return str(val)

    if hasattr(result, "payload") and isinstance(result.payload, dict):
        chunk_id = result.payload.get("chunk_id")
        if chunk_id:
            return str(chunk_id)

    raise ValueError(f"Could not find chunk ID in retrieval result: {result}")


class RRFFusion:
    """Pure computational component that combines ranked retrieval lists using RRF."""

    def __init__(
        self,
        k: Optional[int] = None,
        weights: Optional[Sequence[float]] = None,
    ) -> None:
        """Initialize RRF Fusion with constant k and optional list weights.

        Args:
            k: RRF smoothing constant (default: settings.rrf_k or 60).
            weights: Optional weighting factors for each ranked list (e.g. [0.8, 0.2]).
        """
        self.k: int = k if k is not None else getattr(settings, "rrf_k", DEFAULT_RRF_K)
        self.weights: Optional[List[float]] = [float(w) for w in weights] if weights is not None else None

    def fuse(
        self,
        ranked_lists: Sequence[Sequence[Union[RetrievedChunk, Dict[str, Any]]]],
        top_k: Optional[int] = None,
        weights: Optional[Sequence[float]] = None,
    ) -> List[RetrievedChunk]:
        """Combine multiple ranked candidate lists into a single ranked list using RRF.

        Formula for each item:
            RRF_score(d) = sum_{list in ranked_lists} (weight * 1.0 / (k + rank(d, list)))

        Args:
            ranked_lists: Sequence of ranked result lists (e.g. [dense_results, bm25_results]).
            top_k: Maximum number of fused results to return.
            weights: Optional per-list weights overriding instance weights.

        Returns:
            List of fused RetrievedChunk instances sorted by descending RRF score.
        """
        if not ranked_lists:
            return []

        limit = top_k if top_k is not None else DEFAULT_TOP_K

        active_weights = [float(w) for w in weights] if weights is not None else self.weights
        if active_weights is None:
            active_weights = [1.0] * len(ranked_lists)
        elif len(active_weights) != len(ranked_lists):
            raise ValueError(
                f"Number of weights ({len(active_weights)}) does not match number of ranked lists ({len(ranked_lists)})."
            )

        scores: Dict[str, float] = {}
        documents: Dict[str, Union[RetrievedChunk, Dict[str, Any]]] = {}
        dense_scores: Dict[str, float] = {}
        bm25_scores: Dict[str, float] = {}
        dense_ranks: Dict[str, int] = {}
        bm25_ranks: Dict[str, int] = {}

        for list_idx, results in enumerate(ranked_lists):
            w = active_weights[list_idx]
            seen_in_current_list = set()
            for rank, result in enumerate(results, start=1):
                chunk_id = get_chunk_id(result)
                if chunk_id in seen_in_current_list:
                    continue
                seen_in_current_list.add(chunk_id)
                rrf_score = w * (1.0 / (self.k + rank))

                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score

                if chunk_id not in documents:
                    documents[chunk_id] = result

                # Preserve component scores and ranks if available
                d_score = getattr(result, "dense_score", None)
                if d_score is None and isinstance(result, dict):
                    d_score = result.get("dense_score")
                if d_score is not None:
                    dense_scores[chunk_id] = d_score
                    if chunk_id not in dense_ranks:
                        dense_ranks[chunk_id] = rank

                b_score = getattr(result, "bm25_score", None)
                if b_score is None and isinstance(result, dict):
                    b_score = result.get("bm25_score")
                if b_score is not None:
                    bm25_scores[chunk_id] = b_score
                    if chunk_id not in bm25_ranks:
                        bm25_ranks[chunk_id] = rank

        # Sort descending by RRF score, breaking ties alphabetically by chunk_id
        ranked_chunk_ids = sorted(
            scores.keys(),
            key=lambda cid: (-scores[cid], str(cid)),
        )

        fused_results: List[RetrievedChunk] = []

        for rank, chunk_id in enumerate(ranked_chunk_ids[:limit], start=1):
            original = documents[chunk_id]
            final_score = scores[chunk_id]

            if isinstance(original, RetrievedChunk):
                chunk = original.copy()
                chunk.score = final_score
                chunk.rrf_score = final_score
                if chunk_id in dense_scores:
                    chunk.dense_score = dense_scores[chunk_id]
                if chunk_id in bm25_scores:
                    chunk.bm25_score = bm25_scores[chunk_id]
                if chunk_id in dense_ranks:
                    chunk["dense_rank"] = dense_ranks[chunk_id]
                if chunk_id in bm25_ranks:
                    chunk["bm25_rank"] = bm25_ranks[chunk_id]
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
                    dense_score=dense_scores.get(chunk_id, original.get("dense_score")),
                    bm25_score=bm25_scores.get(chunk_id, original.get("bm25_score")),
                    metadata=metadata,
                )
                if chunk_id in dense_ranks:
                    chunk["dense_rank"] = dense_ranks[chunk_id]
                if chunk_id in bm25_ranks:
                    chunk["bm25_rank"] = bm25_ranks[chunk_id]
                chunk["rrf_rank"] = rank
                fused_results.append(chunk)

        return fused_results


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Union[RetrievedChunk, Dict[str, Any]]]],
    top_k: int = DEFAULT_TOP_K,
    k: int = DEFAULT_RRF_K,
    weights: Optional[Sequence[float]] = None,
) -> List[RetrievedChunk]:
    """Functional interface for Reciprocal Rank Fusion, preserving backwards compatibility."""
    fusion = RRFFusion(k=k, weights=weights)
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
