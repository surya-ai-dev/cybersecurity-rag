from pathlib import Path
import json

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from bm25_retriever import load_documents, BM25Retriever
from rrf_fusion import reciprocal_rank_fusion


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

QUESTIONS_FILE = PROJECT_ROOT / "evaluation_questions.json"
GROUND_TRUTH_FILE = PROJECT_ROOT / "retrieval_ground_truth.json"

QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
COLLECTION_NAME = "cybersecurity_chunks"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

DENSE_TOP_K = 20
BM25_TOP_K = 20
RRF_TOP_K = 20
EVALUATION_TOP_K = 5


# ============================================================
# LOAD JSON FILE
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# EXTRACT QUESTIONS
# ============================================================

def get_questions(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["questions", "evaluation_questions", "data"]:
            if key in data:
                return data[key]

    raise ValueError("Could not find questions in evaluation_questions.json")


# ============================================================
# EXTRACT GROUND TRUTH
# ============================================================

def get_ground_truth(data):
    if isinstance(data, dict):
        return data

    if isinstance(data, list):
        result = {}

        for item in data:
            question_id = item.get("question_id") or item.get("id")

            relevant_ids = (
                item.get("relevant_chunk_ids")
                or item.get("relevant_chunks")
                or item.get("ground_truth")
            )

            if question_id is not None:
                result[str(question_id)] = relevant_ids

        return result

    raise ValueError("Could not read ground truth format")


# ============================================================
# GET QUESTION ID
# ============================================================

def get_question_id(question):
    return str(
        question.get("question_id")
        or question.get("id")
    )


# ============================================================
# GET QUESTION TEXT
# ============================================================

def get_question_text(question):
    return (
        question.get("question")
        or question.get("query")
        or question.get("text")
    )


# ============================================================
# DENSE RETRIEVAL
# ============================================================

def dense_retrieve(client, model, query, top_k=20):

    query_embedding = model.encode(
        query,
        normalize_embeddings=True
    )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding.tolist(),
        limit=top_k,
        with_payload=True
    ).points

    output = []

    for point in results:

        payload = point.payload or {}

        chunk_id = payload.get("chunk_id")

        if chunk_id is None:
            continue

        output.append({
            "chunk_id": chunk_id,
            "score": float(point.score),
            "text": payload.get("text", ""),
            "metadata": payload.get("metadata", {})
        })

    return output


# ============================================================
# RETRIEVAL METRICS
# ============================================================

def calculate_metrics(results, relevant_ids):

    retrieved_ids = [
        str(result["chunk_id"])
        for result in results
    ]

    relevant_ids = set(str(x) for x in relevant_ids)

    # Hit@1
    hit_at_1 = (
        1
        if any(
            chunk_id in relevant_ids
            for chunk_id in retrieved_ids[:1]
        )
        else 0
    )

    # Hit@3
    hit_at_3 = (
        1
        if any(
            chunk_id in relevant_ids
            for chunk_id in retrieved_ids[:3]
        )
        else 0
    )

    # Hit@5
    hit_at_5 = (
        1
        if any(
            chunk_id in relevant_ids
            for chunk_id in retrieved_ids[:5]
        )
        else 0
    )

    # Precision@5
    top_5 = retrieved_ids[:5]

    relevant_in_top_5 = sum(
        1
        for chunk_id in top_5
        if chunk_id in relevant_ids
    )

    precision_at_5 = relevant_in_top_5 / 5

    # MRR
    reciprocal_rank = 0.0

    for rank, chunk_id in enumerate(retrieved_ids, start=1):

        if chunk_id in relevant_ids:
            reciprocal_rank = 1.0 / rank
            break

    return {
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "hit_at_5": hit_at_5,
        "precision_at_5": precision_at_5,
        "mrr": reciprocal_rank
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("RRF RETRIEVAL EVALUATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load questions
    # --------------------------------------------------------

    print("\nLoading evaluation questions...")

    questions_data = load_json(QUESTIONS_FILE)
    questions = get_questions(questions_data)[:15]

    print(f"Loaded {len(questions)} questions.")

    # --------------------------------------------------------
    # Load ground truth
    # --------------------------------------------------------

    print("\nLoading ground truth...")

    ground_truth_data = load_json(GROUND_TRUTH_FILE)
    ground_truth = get_ground_truth(ground_truth_data)

    print("Ground truth loaded.")

    # --------------------------------------------------------
    # Load BM25 documents
    # --------------------------------------------------------

    print("\nLoading documents for BM25...")

    documents = load_documents()

    print(f"Loaded {len(documents):,} documents/chunks.")

    bm25 = BM25Retriever(documents)

    # --------------------------------------------------------
    # Load BGE model
    # --------------------------------------------------------

    print("\nLoading BGE embedding model...")

    model = SentenceTransformer(EMBEDDING_MODEL)

    print("BGE model loaded.")

    # --------------------------------------------------------
    # Connect Qdrant
    # --------------------------------------------------------

    print("\nConnecting to Qdrant...")

    client = QdrantClient(path=str(QDRANT_PATH))

    print(f"Connected to collection: {COLLECTION_NAME}")

    # --------------------------------------------------------
    # Store metrics
    # --------------------------------------------------------

    total_hit_1 = 0
    total_hit_3 = 0
    total_hit_5 = 0
    total_precision_5 = 0.0
    total_mrr = 0.0

    # --------------------------------------------------------
    # Evaluate each question
    # --------------------------------------------------------

    for question_number, question in enumerate(questions, start=1):

        question_id = get_question_id(question)
        query = get_question_text(question)

        print("\n" + "-" * 70)
        print(f"Question {question_number}: {question_id}")
        print(f"Query: {query}")

        relevant_ids = ground_truth.get(question_id, {}).get("relevant_chunks", [])
        if not relevant_ids:
            print("WARNING: No ground-truth chunks found.")
            continue

        # ----------------------------------------------------
        # Dense Top-20
        # ----------------------------------------------------

        dense_results = dense_retrieve(
            client,
            model,
            query,
            DENSE_TOP_K
        )

        # ----------------------------------------------------
        # BM25 Top-20
        # ----------------------------------------------------

        bm25_results = bm25.retrieve(
            query,
            BM25_TOP_K
        )

        # ----------------------------------------------------
        # RRF Fusion
        # ----------------------------------------------------

        fused_results = reciprocal_rank_fusion(
            [
                dense_results,
                bm25_results
            ],
            top_k=RRF_TOP_K
        )

        # ----------------------------------------------------
        # Evaluate RRF Top-5
        # ----------------------------------------------------

        metrics = calculate_metrics(
            fused_results,
            relevant_ids
        )

        total_hit_1 += metrics["hit_at_1"]
        total_hit_3 += metrics["hit_at_3"]
        total_hit_5 += metrics["hit_at_5"]
        total_precision_5 += metrics["precision_at_5"]
        total_mrr += metrics["mrr"]

        # ----------------------------------------------------
        # Print RRF ranking
        # ----------------------------------------------------

        print("\nRRF Top 5:")

        for rank, result in enumerate(
            fused_results[:5],
            start=1
        ):

            chunk_id = result["chunk_id"]
            rrf_score = result.get("rrf_score", 0)

            is_relevant = (
                str(chunk_id) in
                set(str(x) for x in relevant_ids)
            )

            marker = "✓" if is_relevant else "✗"

            print(
                f"  {rank}. "
                f"{marker} "
                f"{chunk_id} "
                f"(RRF={rrf_score:.6f})"
            )

        print("\nMetrics:")

        print(
            f"  Hit@1       : "
            f"{metrics['hit_at_1']}"
        )

        print(
            f"  Hit@3       : "
            f"{metrics['hit_at_3']}"
        )

        print(
            f"  Hit@5       : "
            f"{metrics['hit_at_5']}"
        )

        print(
            f"  Precision@5 : "
            f"{metrics['precision_at_5']:.2f}"
        )

        print(
            f"  MRR         : "
            f"{metrics['mrr']:.4f}"
        )

    # --------------------------------------------------------
    # Final metrics
    # --------------------------------------------------------

    total_questions = len(questions)

    print("\n")
    print("=" * 70)
    print("RRF FINAL RESULTS")
    print("=" * 70)

    print(
        f"\nHit@1       : "
        f"{total_hit_1 / total_questions * 100:.2f}%"
    )

    print(
        f"Hit@3       : "
        f"{total_hit_3 / total_questions * 100:.2f}%"
    )

    print(
        f"Hit@5       : "
        f"{total_hit_5 / total_questions * 100:.2f}%"
    )

    print(
        f"Precision@5 : "
        f"{total_precision_5 / total_questions:.2f}"
    )

    print(
        f"MRR         : "
        f"{total_mrr / total_questions:.4f}"
    )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()