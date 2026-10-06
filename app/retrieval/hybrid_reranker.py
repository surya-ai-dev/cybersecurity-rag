import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from sentence_transformers import CrossEncoder


# ============================================================
# CONFIG
# ============================================================

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

VECTOR_WEIGHT = 0.4
RERANKER_WEIGHT = 0.6

TOP_N = 5


# ============================================================
# LOAD RERANKER
# ============================================================

print("=" * 70)
print("HYBRID RERANKER")
print("=" * 70)

print("\nLoading reranker model...")

reranker = CrossEncoder(RERANKER_MODEL_NAME)

print("✅ Reranker loaded")


# ============================================================
# NORMALIZE SCORES
# ============================================================

def min_max_normalize(scores):
    """
    Convert scores to the range 0-1.
    """

    if not scores:
        return []

    minimum = min(scores)
    maximum = max(scores)

    if maximum == minimum:
        return [1.0] * len(scores)

    return [
        (score - minimum) / (maximum - minimum)
        for score in scores
    ]


# ============================================================
# HYBRID RERANKING
# ============================================================

def hybrid_rerank(
    question,
    documents,
    top_n=TOP_N,
    vector_weight=VECTOR_WEIGHT,
    reranker_weight=RERANKER_WEIGHT
):

    if not documents:
        return []

    # --------------------------------------------------------
    # 1. Get reranker scores
    # --------------------------------------------------------

    pairs = [
        (question, document["text"])
        for document in documents
    ]

    print(
        f"\nReranking {len(documents)} documents..."
    )

    reranker_scores = reranker.predict(pairs)

    # --------------------------------------------------------
    # 2. Extract vector scores
    # --------------------------------------------------------

    vector_scores = [
        float(document["score"])
        for document in documents
    ]

    reranker_scores = [
        float(score)
        for score in reranker_scores
    ]

    # --------------------------------------------------------
    # 3. Normalize both scores
    # --------------------------------------------------------

    normalized_vector = min_max_normalize(
        vector_scores
    )

    normalized_reranker = min_max_normalize(
        reranker_scores
    )

    # --------------------------------------------------------
    # 4. Calculate hybrid score
    # --------------------------------------------------------

    results = []

    for (
        document,
        vector_score,
        reranker_score,
        vector_norm,
        reranker_norm
    ) in zip(
        documents,
        vector_scores,
        reranker_scores,
        normalized_vector,
        normalized_reranker
    ):

        hybrid_score = (
            vector_weight * vector_norm
            +
            reranker_weight * reranker_norm
        )

        results.append(
            {
                **document,

                "vector_score": vector_score,

                "reranker_score": reranker_score,

                "normalized_vector_score":
                    vector_norm,

                "normalized_reranker_score":
                    reranker_norm,

                "hybrid_score":
                    hybrid_score
            }
        )

    # --------------------------------------------------------
    # 5. Sort by hybrid score
    # --------------------------------------------------------

    results.sort(
        key=lambda item: item["hybrid_score"],
        reverse=True
    )

    return results[:top_n]


# ============================================================
# TEST
# ============================================================

def main():

    question = (
        "Why is governance important "
        "for public cloud security?"
    )

    documents = [

        {
            "chunk_id": "chunk_1",

            "score": 0.80,

            "text": (
                "Cloud computing provides "
                "on-demand access to computing "
                "resources."
            )
        },

        {
            "chunk_id": "chunk_2",

            "score": 0.82,

            "text": (
                "Organizations should maintain "
                "governance, policies, procedures, "
                "standards, auditing, and monitoring "
                "throughout the cloud service lifecycle."
            )
        },

        {
            "chunk_id": "chunk_3",

            "score": 0.79,

            "text": (
                "Public cloud computing uses "
                "shared computing resources."
            )
        },

        {
            "chunk_id": "chunk_4",

            "score": 0.81,

            "text": (
                "Organizations remain accountable "
                "for security and privacy and should "
                "oversee how cloud providers maintain "
                "the computing environment."
            )
        }
    ]

    print("\nQuestion:")
    print(question)

    results = hybrid_rerank(
        question,
        documents,
        top_n=TOP_N
    )

    print("\n")
    print("=" * 70)
    print("HYBRID RERANKED RESULTS")
    print("=" * 70)

    for rank, result in enumerate(
        results,
        start=1
    ):

        print("\n" + "-" * 70)

        print(
            f"Rank                    : {rank}"
        )

        print(
            f"Chunk ID                : "
            f"{result['chunk_id']}"
        )

        print(
            f"Vector score            : "
            f"{result['vector_score']:.4f}"
        )

        print(
            f"Reranker score          : "
            f"{result['reranker_score']:.4f}"
        )

        print(
            f"Normalized vector      : "
            f"{result['normalized_vector_score']:.4f}"
        )

        print(
            f"Normalized reranker    : "
            f"{result['normalized_reranker_score']:.4f}"
        )

        print(
            f"Hybrid score            : "
            f"{result['hybrid_score']:.4f}"
        )

        print("\nText:")

        print(result["text"])

    print("\n")
    print("=" * 70)
    print("HYBRID RERANKER TEST COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()