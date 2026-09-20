import sys
import json

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

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

GROUND_TRUTH_FILE = "retrieval_ground_truth.json"


# ============================================================
# LOAD QUESTIONS
# ============================================================

def load_questions():

    with open(
        QUESTIONS_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)[:15]


# ============================================================
# LOAD GROUND TRUTH
# ============================================================

def load_ground_truth():

    with open(
        GROUND_TRUTH_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# LOAD EMBEDDING MODEL
# ============================================================

print("=" * 70)
print("RAG RETRIEVAL METRICS EVALUATION")
print("=" * 70)

print("\nLoading BGE-small...")

model = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)

print("BGE-small loaded")


# ============================================================
# CONNECT QDRANT
# ============================================================

print("\nConnecting to Qdrant...")

client = QdrantClient(
    path=QDRANT_PATH
)

print("Qdrant connected")


# ============================================================
# RETRIEVE DOCUMENTS
# ============================================================

def retrieve_documents(question):

    query_vector = model.encode(
        question,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector.tolist(),
        limit=TOP_K,
        with_payload=True
    ).points

    return results


# ============================================================
# GET CHUNK IDS
# ============================================================

def get_chunk_ids(results):

    chunk_ids = []

    for result in results:

        payload = result.payload or {}

        chunk_id = payload.get(
            "chunk_id"
        )

        if chunk_id:
            chunk_ids.append(chunk_id)

    return chunk_ids


# ============================================================
# HIT@K
# ============================================================

def calculate_hit_at_k(
    retrieved_chunks,
    relevant_chunks,
    k
):

    retrieved_top_k = retrieved_chunks[:k]

    for chunk_id in retrieved_top_k:

        if chunk_id in relevant_chunks:
            return 1

    return 0


# ============================================================
# PRECISION@K
# ============================================================

def calculate_precision_at_k(
    retrieved_chunks,
    relevant_chunks,
    k
):

    retrieved_top_k = retrieved_chunks[:k]

    if not retrieved_top_k:
        return 0.0

    relevant_count = 0

    for chunk_id in retrieved_top_k:

        if chunk_id in relevant_chunks:
            relevant_count += 1

    return relevant_count / len(retrieved_top_k)


# ============================================================
# MRR
# ============================================================

def calculate_mrr(
    retrieved_chunks,
    relevant_chunks
):

    for rank, chunk_id in enumerate(
        retrieved_chunks,
        start=1
    ):

        if chunk_id in relevant_chunks:

            return 1 / rank

    return 0.0


# ============================================================
# MAIN EVALUATION
# ============================================================

def main():

    questions = load_questions()

    ground_truth = load_ground_truth()

    print(
        f"\nLoaded {len(questions)} evaluation questions."
    )

    print(
        f"Loaded ground truth for "
        f"{len(ground_truth)} questions."
    )

    print("\nStarting evaluation...")

    # --------------------------------------------------------
    # Store metrics
    # --------------------------------------------------------

    hit_at_1_scores = []

    hit_at_3_scores = []

    hit_at_5_scores = []

    precision_at_5_scores = []

    mrr_scores = []


    # --------------------------------------------------------
    # Evaluate each question
    # --------------------------------------------------------

    for question_item in questions:

        question_id = question_item["id"]

        question = question_item["question"]

        print("\n")
        print("=" * 70)

        print(
            f"{question_id}"
        )

        print("=" * 70)

        print(
            f"\nQuestion:\n{question}"
        )

        # ----------------------------------------------------
        # Retrieve
        # ----------------------------------------------------

        results = retrieve_documents(
            question
        )

        retrieved_chunks = get_chunk_ids(
            results
        )

        # ----------------------------------------------------
        # Ground truth
        # ----------------------------------------------------

        question_ground_truth = ground_truth.get(
            question_id,
            {}
        )

        relevant_chunks = question_ground_truth.get(
            "relevant_chunks",
            []
        )

        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        hit_1 = calculate_hit_at_k(
            retrieved_chunks,
            relevant_chunks,
            1
        )

        hit_3 = calculate_hit_at_k(
            retrieved_chunks,
            relevant_chunks,
            3
        )

        hit_5 = calculate_hit_at_k(
            retrieved_chunks,
            relevant_chunks,
            5
        )

        precision_5 = calculate_precision_at_k(
            retrieved_chunks,
            relevant_chunks,
            5
        )

        mrr = calculate_mrr(
            retrieved_chunks,
            relevant_chunks
        )

        # ----------------------------------------------------
        # Store
        # ----------------------------------------------------

        hit_at_1_scores.append(
            hit_1
        )

        hit_at_3_scores.append(
            hit_3
        )

        hit_at_5_scores.append(
            hit_5
        )

        precision_at_5_scores.append(
            precision_5
        )

        mrr_scores.append(
            mrr
        )

        # ----------------------------------------------------
        # Display retrieved chunks
        # ----------------------------------------------------

        print("\nRetrieved chunks:")

        for rank, chunk_id in enumerate(
            retrieved_chunks,
            start=1
        ):

            marker = ""

            if chunk_id in relevant_chunks:
                marker = " ✅ RELEVANT"
            else:
                marker = " ❌"

            print(
                f"  Rank {rank}: "
                f"{chunk_id}"
                f"{marker}"
            )

        # ----------------------------------------------------
        # Display ground truth
        # ----------------------------------------------------

        print("\nRelevant chunks:")

        for chunk_id in relevant_chunks:

            print(
                f"  ✅ {chunk_id}"
            )

        # ----------------------------------------------------
        # Display metrics
        # ----------------------------------------------------

        print("\nMetrics:")

        print(
            f"  Hit@1       : "
            f"{'YES' if hit_1 else 'NO'}"
        )

        print(
            f"  Hit@3       : "
            f"{'YES' if hit_3 else 'NO'}"
        )

        print(
            f"  Hit@5       : "
            f"{'YES' if hit_5 else 'NO'}"
        )

        print(
            f"  Precision@5 : "
            f"{precision_5:.4f}"
        )

        print(
            f"  MRR         : "
            f"{mrr:.4f}"
        )


    # ========================================================
    # OVERALL METRICS
    # ========================================================

    total_questions = len(questions)

    hit_at_1 = (
        sum(hit_at_1_scores)
        / total_questions
    )

    hit_at_3 = (
        sum(hit_at_3_scores)
        / total_questions
    )

    hit_at_5 = (
        sum(hit_at_5_scores)
        / total_questions
    )

    precision_at_5 = (
        sum(precision_at_5_scores)
        / total_questions
    )

    mrr = (
        sum(mrr_scores)
        / total_questions
    )


    # ========================================================
    # FINAL RESULTS
    # ========================================================

    print("\n")

    print("=" * 70)
    print("OVERALL RETRIEVAL METRICS")
    print("=" * 70)

    print(
        f"\nQuestions tested : "
        f"{total_questions}"
    )

    print(
        f"\nHit@1"
    )

    print(
        f"  {hit_at_1:.2%}"
    )

    print(
        f"\nHit@3"
    )

    print(
        f"  {hit_at_3:.2%}"
    )

    print(
        f"\nHit@5"
    )

    print(
        f"  {hit_at_5:.2%}"
    )

    print(
        f"\nPrecision@5"
    )

    print(
        f"  {precision_at_5:.2%}"
    )

    print(
        f"\nMRR"
    )

    print(
        f"  {mrr:.4f}"
    )

    print("\n")

    print("=" * 70)
    print("WHAT THESE METRICS MEAN")
    print("=" * 70)

    print(
        "\nHit@1:"
    )

    print(
        "Did the first retrieved chunk contain "
        "relevant information?"
    )

    print(
        "\nHit@3:"
    )

    print(
        "Did at least one of the top 3 chunks "
        "contain relevant information?"
    )

    print(
        "\nHit@5:"
    )

    print(
        "Did at least one of the top 5 chunks "
        "contain relevant information?"
    )

    print(
        "\nPrecision@5:"
    )

    print(
        "How many of the top 5 retrieved chunks "
        "were relevant?"
    )

    print(
        "\nMRR:"
    )

    print(
        "How high was the first relevant chunk "
        "in the ranking?"
    )

    print("\n")

    print("=" * 70)
    print("RETRIEVAL METRICS EVALUATION COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()