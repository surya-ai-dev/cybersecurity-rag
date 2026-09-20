"""
RRF Fusion
==========
Combines ranked results from multiple retrievers using
Reciprocal Rank Fusion (RRF).

Architecture:

Dense Retrieval Top-K
        +
BM25 Retrieval Top-K
        |
        v
    RRF Fusion
        |
        v
 Combined Ranked Results
"""


from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

RRF_K = 60

DEFAULT_TOP_K = 20


# ============================================================
# CHUNK ID EXTRACTION
# ============================================================

def get_chunk_id(result: dict[str, Any]) -> str:
    """
    Extract the chunk ID from a retrieval result.

    Expected result format:

    {
        "chunk_id": "NIST_SP_800-144_00080",
        ...
    }

    We also support a few common alternative field names
    to make the fusion layer robust.
    """

    possible_keys = [
        "chunk_id",
        "id",
        "document_id",
    ]

    for key in possible_keys:
        value = result.get(key)

        if value is not None:
            return str(value)

    raise ValueError(
        f"Could not find chunk ID in retrieval result: {result}"
    )


# ============================================================
# RRF FUSION
# ============================================================

def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    top_k: int = DEFAULT_TOP_K,
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """
    Combine multiple ranked retrieval lists using RRF.

    Parameters
    ----------
    ranked_lists:
        List of ranked result lists.

        Example:

        [
            dense_results,
            bm25_results
        ]

    top_k:
        Number of final results to return.

    k:
        RRF constant. Usually 60.

    Returns
    -------
    list[dict]
        Fused and ranked results.
    """

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    if not ranked_lists:
        return []

    # --------------------------------------------------------
    # Store RRF scores
    # --------------------------------------------------------

    scores: dict[str, float] = {}

    # Store the original result object for each chunk
    documents: dict[str, dict[str, Any]] = {}

    # --------------------------------------------------------
    # Process every retriever
    # --------------------------------------------------------

    for results in ranked_lists:

        for rank, result in enumerate(results, start=1):

            chunk_id = get_chunk_id(result)

            # RRF formula:
            #
            # score += 1 / (k + rank)

            rrf_score = 1.0 / (k + rank)

            scores[chunk_id] = (
                scores.get(chunk_id, 0.0)
                + rrf_score
            )

            # Keep the first complete result object
            if chunk_id not in documents:
                documents[chunk_id] = dict(result)

    # --------------------------------------------------------
    # Sort by RRF score
    # --------------------------------------------------------

    ranked_chunk_ids = sorted(
        scores.keys(),
        key=lambda chunk_id: scores[chunk_id],
        reverse=True,
    )

    # --------------------------------------------------------
    # Build final results
    # --------------------------------------------------------

    fused_results = []

    for rank, chunk_id in enumerate(
        ranked_chunk_ids[:top_k],
        start=1,
    ):

        result = dict(documents[chunk_id])

        result["rrf_score"] = scores[chunk_id]

        result["rrf_rank"] = rank

        fused_results.append(result)

    return fused_results


# ============================================================
# DEBUG / DISPLAY
# ============================================================

def print_fusion_results(
    results: list[dict[str, Any]],
    title: str = "RRF RESULTS",
) -> None:
    """
    Pretty-print fused retrieval results.
    """

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)

    if not results:
        print("No results.")
        return

    for result in results:

        chunk_id = get_chunk_id(result)

        rank = result.get(
            "rrf_rank",
            "?",
        )

        score = result.get(
            "rrf_score",
            0.0,
        )

        print(
            f"{rank:>2}. "
            f"{chunk_id:<40} "
            f"RRF={score:.6f}"
        )


# ============================================================
# SIMPLE TEST
# ============================================================

def main():

    print("=" * 70)
    print("RRF FUSION TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # Fake Dense results
    # --------------------------------------------------------

    dense_results = [
        {
            "chunk_id": "A",
            "text": "Dense result A",
        },
        {
            "chunk_id": "B",
            "text": "Dense result B",
        },
        {
            "chunk_id": "C",
            "text": "Dense result C",
        },
        {
            "chunk_id": "D",
            "text": "Dense result D",
        },
        {
            "chunk_id": "E",
            "text": "Dense result E",
        },
    ]

    # --------------------------------------------------------
    # Fake BM25 results
    # --------------------------------------------------------

    bm25_results = [
        {
            "chunk_id": "C",
            "text": "BM25 result C",
        },
        {
            "chunk_id": "A",
            "text": "BM25 result A",
        },
        {
            "chunk_id": "F",
            "text": "BM25 result F",
        },
        {
            "chunk_id": "B",
            "text": "BM25 result B",
        },
        {
            "chunk_id": "G",
            "text": "BM25 result G",
        },
    ]

    # --------------------------------------------------------
    # Run RRF
    # --------------------------------------------------------

    fused_results = reciprocal_rank_fusion(
        ranked_lists=[
            dense_results,
            bm25_results,
        ],
        top_k=5,
    )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print_fusion_results(
        fused_results,
        title="RRF FUSED RESULTS",
    )

    print()
    print("✅ RRF fusion test completed.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()