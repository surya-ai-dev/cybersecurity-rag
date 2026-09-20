import sys
import json

# ============================================================
# WINDOWS UTF-8 OUTPUT FIX
# ============================================================

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass


from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient


# ============================================================
# CONFIG
# ============================================================

QDRANT_PATH = "data/qdrant"

COLLECTION_NAME = "cybersecurity_chunks"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

TOP_K = 5

QUESTIONS_FILE = "evaluation_questions.json"

TEXT_PREVIEW_LENGTH = 800


# ============================================================
# LOAD QUESTIONS
# ============================================================

def load_questions():

    with open(
        QUESTIONS_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        questions = json.load(file)

    if not isinstance(questions, list):
        raise ValueError(
            "evaluation_questions.json must contain a list."
        )

    return questions[:15]  # Limit to first 15 questions for evaluation


# ============================================================
# LOAD EMBEDDING MODEL
# ============================================================

print("=" * 70)
print("RAG RETRIEVAL EVALUATION")
print("=" * 70)

print("\nLoading BGE-small...")

model = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)

print("BGE-small loaded")


# ============================================================
# CONNECT TO QDRANT
# ============================================================

print("\nConnecting to Qdrant...")

client = QdrantClient(
    path=QDRANT_PATH
)

print("Qdrant connected")


# ============================================================
# VERIFY COLLECTION
# ============================================================

print("\nChecking Qdrant collection...")

try:

    collection_info = client.get_collection(
        collection_name=COLLECTION_NAME
    )

    print(
        f"Collection       : {COLLECTION_NAME}"
    )

    print(
        f"Vectors           : "
        f"{collection_info.points_count}"
    )

except Exception as error:

    print(
        "\nERROR: Could not access Qdrant collection."
    )

    print(
        f"Details: {error}"
    )

    sys.exit(1)


# ============================================================
# RETRIEVE DOCUMENTS
# ============================================================

def retrieve_documents(question):

    # --------------------------------------------------------
    # Generate query embedding
    # --------------------------------------------------------

    query_vector = model.encode(
        question,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    # --------------------------------------------------------
    # Search Qdrant
    # --------------------------------------------------------

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector.tolist(),
        limit=TOP_K,
        with_payload=True
    ).points

    return results


# ============================================================
# DISPLAY SINGLE RESULT
# ============================================================

def display_result(
    rank,
    result
):

    payload = result.payload or {}

    print("\n" + "-" * 70)

    print(
        f"Rank        : {rank}"
    )

    print(
        f"Similarity  : {result.score:.4f}"
    )

    print(
        f"Chunk ID     : "
        f"{payload.get('chunk_id', 'N/A')}"
    )

    print(
        f"Document     : "
        f"{payload.get('document_id', 'N/A')}"
    )

    print(
        f"Category     : "
        f"{payload.get('category', 'N/A')}"
    )

    print(
        f"Section      : "
        f"{payload.get('section', 'N/A')}"
    )

    text = payload.get(
        "text",
        ""
    )

    print("\nText preview:")

    if text:

        print(
            text[:TEXT_PREVIEW_LENGTH]
        )

    else:

        print(
            "[No text found in payload]"
        )


# ============================================================
# DISPLAY QUESTION RESULTS
# ============================================================

def display_results(
    question_id,
    question,
    results
):

    print("\n")
    print("=" * 70)

    print(
        f"QUESTION {question_id}"
    )

    print("=" * 70)

    print(
        f"\nQuestion:\n{question}"
    )

    print(
        f"\nRetrieved {len(results)} chunks:"
    )

    if not results:

        print(
            "\nWARNING: No chunks were retrieved."
        )

        return

    for rank, result in enumerate(
        results,
        start=1
    ):

        display_result(
            rank,
            result
        )


# ============================================================
# RETRIEVAL SUMMARY
# ============================================================

def calculate_summary(
    evaluation_results
):

    if not evaluation_results:

        return

    all_scores = []

    top_scores = []

    for item in evaluation_results:

        scores = item["scores"]

        if not scores:
            continue

        all_scores.extend(scores)

        top_scores.append(
            scores[0]
        )

    print("\n")
    print("=" * 70)
    print("RETRIEVAL SUMMARY")
    print("=" * 70)

    if all_scores:

        average_score = (
            sum(all_scores)
            / len(all_scores)
        )

        print(
            f"\nAverage similarity score "
            f"(all retrieved chunks): "
            f"{average_score:.4f}"
        )

    if top_scores:

        average_top_score = (
            sum(top_scores)
            / len(top_scores)
        )

        print(
            f"Average top-1 similarity score: "
            f"{average_top_score:.4f}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Load evaluation questions
    # --------------------------------------------------------

    questions = load_questions()

    print(
        f"\nLoaded {len(questions)} "
        "evaluation questions."
    )

    print(
        "\nStarting retrieval evaluation..."
    )

    evaluation_results = []

    # --------------------------------------------------------
    # Evaluate every question
    # --------------------------------------------------------

    for question_item in questions:

        question_id = question_item.get(
            "id",
            "UNKNOWN"
        )

        question = question_item.get(
            "question",
            ""
        ).strip()

        if not question:

            print(
                f"\nWARNING: "
                f"{question_id} has an empty question."
            )

            continue

        print(
            f"\nSearching for: {question}"
        )

        results = retrieve_documents(
            question
        )

        scores = [
            float(result.score)
            for result in results
        ]

        evaluation_results.append(
            {
                "id": question_id,
                "question": question,
                "scores": scores
            }
        )

        display_results(
            question_id,
            question,
            results
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    calculate_summary(
        evaluation_results
    )

    # --------------------------------------------------------
    # Completion
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("RETRIEVAL EVALUATION COMPLETE")
    print("=" * 70)

    print(
        f"\nQuestions tested : "
        f"{len(evaluation_results)}"
    )

    print(
        f"Top-K per question: "
        f"{TOP_K}"
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "The similarity score alone does NOT tell us "
        "whether the retrieved chunk actually answers "
        "the question."
    )

    print(
        "\nNext step:"
    )

    print(
        "Inspect each question and determine whether "
        "the retrieved chunks are relevant."
    )

    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()