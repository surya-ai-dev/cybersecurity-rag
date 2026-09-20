from retriever import retrieve
from reranker import rerank_documents
from build_context import build_context
from llm import generate_answer


# ============================================================
# RAG PIPELINE
# ============================================================

def run_rag(question: str):

    # --------------------------------------------------------
    # STEP 1 — HYBRID RETRIEVAL + RRF
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("STEP 1 — RETRIEVING DOCUMENTS")
    print("=" * 70)

    results = retrieve(
        question,
        top_k=20
    )

    print(
        f"\nRRF candidate documents: {len(results)}"
    )


    # --------------------------------------------------------
    # STEP 2 — CROSS-ENCODER RERANKING
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("STEP 2 — RERANKING DOCUMENTS")
    print("=" * 70)

    reranked_results = rerank_documents(
        question=question,
        documents=results,
        top_n=5
    )

    print(
        f"\nFinal reranked documents: "
        f"{len(reranked_results)}"
    )


    # --------------------------------------------------------
    # STEP 3 — CONTEXT BUILDING
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("STEP 3 — BUILDING CONTEXT")
    print("=" * 70)

    context = build_context(
        reranked_results
    )

    print(
        f"Context built from "
        f"{len(reranked_results)} chunks."
    )


    # --------------------------------------------------------
    # STEP 4 — LLM GENERATION
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("STEP 4 — GENERATING ANSWER")
    print("=" * 70)

    answer = generate_answer(
        question,
        context
    )


    return answer, reranked_results


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("CYBERSECURITY RAG SYSTEM")
    print("=" * 70)

    question = input(
        "\nEnter cybersecurity question: "
    ).strip()

    if not question:

        print("❌ Question cannot be empty.")

        return


    answer, results = run_rag(
        question
    )


    # --------------------------------------------------------
    # FINAL ANSWER
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("FINAL ANSWER")
    print("=" * 70)

    print(answer)


    # --------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("SOURCES")
    print("=" * 70)

    for index, result in enumerate(
        results,
        start=1
    ):

        metadata = result.get(
            "metadata",
            {}
        )

        document = metadata.get(
            "document_id",
            "Unknown"
        )

        source_file = metadata.get(
            "source_file",
            "Unknown"
        )

        section = metadata.get(
            "section",
            "Unknown"
        )

        reranker_score = result.get(
            "reranker_score",
            0.0
        )

        print(
            f"[{index}] "
            f"{document} | "
            f"{source_file}"
        )

        print(
            f"    Section: {section}"
        )

        print(
            f"    Reranker score: "
            f"{reranker_score:.4f}"
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()