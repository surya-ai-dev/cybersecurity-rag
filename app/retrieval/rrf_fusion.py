"""Compatibility wrapper for RRF fusion.

Exposes RRFFusion and reciprocal_rank_fusion from app.retrieval.rrf.
"""

from app.retrieval.rrf import (
    DEFAULT_RRF_K,
    DEFAULT_TOP_K,
    RRFFusion,
    get_chunk_id,
    main,
    print_fusion_results,
    reciprocal_rank_fusion,
)

__all__ = [
    "RRFFusion",
    "reciprocal_rank_fusion",
    "get_chunk_id",
    "print_fusion_results",
    "DEFAULT_RRF_K",
    "DEFAULT_TOP_K",
    "main",
]

if __name__ == "__main__":
    main()