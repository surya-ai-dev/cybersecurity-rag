from sentence_transformers import CrossEncoder


# ============================================================
# CONFIGURATION
# ============================================================

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_TOP_N = 5


# ============================================================
# LOAD RERANKER MODEL
# ============================================================

print("=" * 70)
print("RERANKER")
print("=" * 70)

print("\nLoading reranker model...")

reranker = CrossEncoder(RERANKER_MODEL_NAME)

print("✅ Reranker loaded")


# ============================================================
# RERANK DOCUMENTS
# ============================================================

def rerank_documents(
    question: str,
    documents: list[dict],
    top_n: int = DEFAULT_TOP_N
) -> list[dict]:
    """
    Rerank retrieved documents using a Cross-Encoder.

    Parameters
    ----------
    question : str
        User's question.

    documents : list[dict]
        Retrieved documents. Each document should contain
        a "text" field.

    top_n : int
        Number of documents to return after reranking.

    Returns
    -------
    list[dict]
        Reranked documents with "reranker_score" added.
    """

    if not documents:
        return []

    print(f"\nReranking {len(documents)} documents...")

    # --------------------------------------------------------
    # Create question-document pairs
    # --------------------------------------------------------

    pairs = []

    for document in documents:
        text = document.get("text", "")
        pairs.append((question, text))

    # --------------------------------------------------------
    # Calculate Cross-Encoder scores
    # --------------------------------------------------------

    scores = reranker.predict(
        pairs,
        show_progress_bar=False
    )

    # --------------------------------------------------------
    # Attach scores to documents
    # --------------------------------------------------------

    reranked_documents = []

    for document, score in zip(documents, scores):

        document_copy = document.copy()

        document_copy["reranker_score"] = float(score)

        reranked_documents.append(document_copy)

    # --------------------------------------------------------
    # Sort by reranker score
    # --------------------------------------------------------

    reranked_documents.sort(
        key=lambda x: x["reranker_score"],
        reverse=True
    )

    # --------------------------------------------------------
    # Return Top-N documents
    # --------------------------------------------------------

    return reranked_documents[:top_n]


# ============================================================
# DISPLAY RESULTS
# ============================================================

def display_reranked_results(
    documents: list[dict]
) -> None:
    """
    Display reranked documents for debugging/testing.
    """

    print("\n" + "=" * 70)
    print("RERANKED RESULTS")
    print("=" * 70)

    for index, document in enumerate(documents, start=1):

        metadata = document.get("metadata", {})

        chunk_id = document.get(
            "chunk_id",
            "Unknown"
        )

        document_id = metadata.get(
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

        score = document.get(
            "reranker_score",
            0.0
        )

        print(f"\n[{index}]")
        print(f"Chunk ID: {chunk_id}")
        print(f"Document: {document_id}")
        print(f"Source: {source_file}")
        print(f"Section: {section}")
        print(f"Reranker Score: {score:.4f}")

        text = document.get("text", "")

        print("\nText:")
        print(text[:500])

        print("-" * 70)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_question = (
        "What are the security risks of public cloud computing?"
    )

    test_documents = [
        {
            "chunk_id": "test_001",
            "text": (
                "Public cloud computing introduces security "
                "risks including data exposure, shared "
                "infrastructure, and limited control."
            ),
            "metadata": {
                "document_id": "TEST_DOC",
                "source_file": "test.txt",
                "section": "Security Risks"
            }
        },
        {
            "chunk_id": "test_002",
            "text": (
                "Cloud consumers should understand the "
                "security responsibilities shared between "
                "the provider and the consumer."
            ),
            "metadata": {
                "document_id": "TEST_DOC",
                "source_file": "test.txt",
                "section": "Responsibilities"
            }
        },
        {
            "chunk_id": "test_003",
            "text": (
                "Public cloud environments can introduce "
                "multi-tenancy and monitoring challenges."
            ),
            "metadata": {
                "document_id": "TEST_DOC",
                "source_file": "test.txt",
                "section": "Cloud Security"
            }
        }
    ]

    results = rerank_documents(
        question=test_question,
        documents=test_documents,
        top_n=3
    )

    display_reranked_results(results)