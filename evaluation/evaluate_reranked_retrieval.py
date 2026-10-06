import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient

from app.retrieval.bm25_retriever import load_documents, BM25Retriever
from app.retrieval.rrf_fusion import reciprocal_rank_fusion

# ============================================================
# CONFIG
# ============================================================

QDRANT_PATH = str(PROJECT_ROOT / "data" / "qdrant")

COLLECTION_NAME = "cybersecurity_chunks"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

QUESTIONS_FILE = PROJECT_ROOT / "data" / "evaluation" / "evaluation_questions.json"

GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth.json"

DENSE_TOP_K = 20
BM25_TOP_K = 20
RRF_TOP_K = 20
FINAL_TOP_K = 10

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
# GET RELEVANT CHUNK IDS
# ============================================================

def get_relevant_chunk_ids(ground_truth_item):

    # Supports the ground-truth structure we have been using:
    #
    # {
    #     "Q1": {
    #         "relevant_chunks": [...]
    #     }
    # }
    #
    # Also handles:
    #
    # {
    #     "Q1": [...]
    # }

    if isinstance(
        ground_truth_item,
        dict
    ):

        relevant_chunks = (
            ground_truth_item.get(
                "relevant_chunks",
                ground_truth_item.get(
                    "relevant_chunk_ids",
                    []
                )
            )
        )

    else:

        relevant_chunks = ground_truth_item

    return set(
        str(chunk_id)
        for chunk_id in relevant_chunks
    )


# ============================================================
# RETRIEVE FROM QDRANT
# ============================================================

def retrieve_documents(
    client,
    model,
    bm25,
    question
):

    # --------------------------------------------------------
    # Dense / BGE retrieval
    # --------------------------------------------------------

    query_vector = model.encode(
        question,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    dense_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector.tolist(),
        limit=DENSE_TOP_K,
        with_payload=True
    ).points

    dense_documents = []

    for result in dense_results:

        payload = result.payload or {}

        chunk_id = payload.get("chunk_id")

        if chunk_id is None:
            continue

        dense_documents.append({
            "chunk_id": chunk_id,
            "score": float(result.score),
            "text": payload.get("text", ""),
            "metadata": payload.get("metadata", {})
        })

    # --------------------------------------------------------
    # BM25 retrieval
    # --------------------------------------------------------

    bm25_results = bm25.retrieve(
        question,
        BM25_TOP_K
    )

    # --------------------------------------------------------
    # RRF Fusion
    # --------------------------------------------------------

    fused_results = reciprocal_rank_fusion(
        [
            dense_documents,
            bm25_results
        ],
        top_k=RRF_TOP_K
    )

    return fused_results


# ============================================================
# RERANK DOCUMENTS
# ============================================================

def rerank_documents(
    reranker,
    question,
    results
):

    documents = []

    for result in results:

        text = result.get("text", "")

        if not text:
            continue

        documents.append(result)

    pairs = [
        [question, document["text"]]
        for document in documents
    ]

    if question == "What security challenges are associated with public cloud environments?":
        print("\nQ2 RERANKER INPUT:")
        for i, pair in enumerate(pairs, start=1):
            print(f"\nCandidate {i}")
            print(f"Question: {pair[0]}")
            print(f"Text: {pair[1][:500]}")

    scores = reranker.predict(
            pairs
        )

    ranked_results = sorted(
        zip(documents, scores),
        key=lambda x: float(x[1]),
        reverse=True
    )

    return ranked_results[:FINAL_TOP_K]


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    ranked_chunk_ids,
    relevant_chunk_ids
):

    # --------------------------------------------------------
    # Hit@1
    # --------------------------------------------------------

    hit_at_1 = (
        len(ranked_chunk_ids) > 0
        and ranked_chunk_ids[0]
        in relevant_chunk_ids
    )

    # --------------------------------------------------------
    # Hit@3
    # --------------------------------------------------------

    hit_at_3 = any(
        chunk_id in relevant_chunk_ids
        for chunk_id in ranked_chunk_ids[:3]
    )

    # --------------------------------------------------------
    # Hit@5
    # --------------------------------------------------------

    hit_at_5 = any(
        chunk_id in relevant_chunk_ids
        for chunk_id in ranked_chunk_ids[:5]
    )

    # --------------------------------------------------------
    # Precision@5
    # --------------------------------------------------------

    top_5 = ranked_chunk_ids[:5]

    relevant_count = sum(
        chunk_id in relevant_chunk_ids
        for chunk_id in top_5
    )

    precision_at_5 = (
        relevant_count / len(top_5)
        if top_5
        else 0.0
    )

    # --------------------------------------------------------
    # MRR
    # --------------------------------------------------------

    reciprocal_rank = 0.0

    for rank, chunk_id in enumerate(
        ranked_chunk_ids,
        start=1
    ):

        if chunk_id in relevant_chunk_ids:

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
    print("RERANKED RETRIEVAL EVALUATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load evaluation questions
    # --------------------------------------------------------

    print("\nLoading evaluation questions...")

    questions = load_questions()

    print(
        f"Loaded {len(questions)} evaluation questions."
    )

    # --------------------------------------------------------
    # Load ground truth
    # --------------------------------------------------------

    print("\nLoading ground truth...")

    ground_truth = load_ground_truth()

    print(
        f"Loaded ground truth for "
        f"{len(ground_truth)} questions."
    )

    # --------------------------------------------------------
    # Load embedding model
    # --------------------------------------------------------

    print("\nLoading BGE-small...")

    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME
    )

    print("BGE-small loaded")
    
    
    print("\nLoading BM25 documents...")

    documents = load_documents()

    bm25 = BM25Retriever(documents)

    print("BM25 loaded")

    # --------------------------------------------------------
    # Load reranker
    # --------------------------------------------------------

    print("\nLoading reranker...")

    reranker = CrossEncoder(
        RERANKER_MODEL_NAME
    )

    print("Reranker loaded")

    # --------------------------------------------------------
    # Connect Qdrant
    # --------------------------------------------------------

    print("\nConnecting to Qdrant...")

    client = QdrantClient(
        path="data/qdrant"
    )
    print("Qdrant connected")

    # --------------------------------------------------------
    # Metric accumulators
    # --------------------------------------------------------

    total_hit_at_1 = 0

    total_hit_at_3 = 0

    total_hit_at_5 = 0

    total_precision_at_5 = 0.0

    total_mrr = 0.0

    # --------------------------------------------------------
    # Evaluate every question
    # --------------------------------------------------------

    print("\nStarting reranked evaluation...")

    for question_item in questions:

        question_id = question_item["id"]

        question = question_item["question"]

        print("\n")
        print("=" * 70)
        print(question_id)
        print("=" * 70)

        print("\nQuestion:")
        print(question)

        # ----------------------------------------------------
        # Ground truth
        # ----------------------------------------------------

        if question_id not in ground_truth:

            print(
                f"\nWARNING: No ground truth found "
                f"for {question_id}"
            )

            continue

        relevant_chunk_ids = get_relevant_chunk_ids(
            ground_truth[question_id]
        )

        print("\nGround-truth relevant chunks:")

        for chunk_id in relevant_chunk_ids:

            print(
                f"  {chunk_id}"
            )

        # ----------------------------------------------------
        # Vector retrieval
        # ----------------------------------------------------

        print(
                f"\nHybrid retrieval → "
                f"Dense Top-{DENSE_TOP_K} + "
                f"BM25 Top-{BM25_TOP_K} → "
                f"RRF Top-{RRF_TOP_K}"
            )

        retrieved_results = retrieve_documents(
                            client,
                            embedding_model,
                            bm25,
                            question
                        )
        print(
            f"Retrieved "
            f"{len(retrieved_results)} candidates."
        )
        if question_id == "Q2":
            print("\nQ2 RRF TOP-20 CANDIDATES:")
            for rank, result in enumerate(retrieved_results, start=1):
                print(
                    f"\nRRF Rank {rank}: "
                    f"{result.get('chunk_id', 'N/A')}"
                )
                print(
                    f"RRF Score: "
                    f"{result.get('rrf_score', 0.0):.6f}"
                )
                print(
                    f"Text: "
                    f"{result.get('text', '')[:300]}"
                )

        # ----------------------------------------------------
        # Reranking
        # ----------------------------------------------------

        print("\nReranking candidates...")

        reranked_results = rerank_documents(
            reranker,
            question,
            retrieved_results
        )

        print(
            f"Selected Top-{len(reranked_results)} "
            f"after reranking."
        )

        # ----------------------------------------------------
        # Extract chunk IDs
        # ----------------------------------------------------

        ranked_chunk_ids = []

        print("\nRERANKED RESULTS:")

        for rank, item in enumerate(
            reranked_results,
            start=1
        ):

            result = item[0]

            reranker_score = float(item[1])
            

            chunk_id = str(
                        result.get(
                            "chunk_id",
                            "N/A"
                        )
                    )
            
            print(
                f"  Rank {rank}: {chunk_id}"
            )

            print(
                f"  Text: {result.get('text', '')[:500]}"
            )

            ranked_chunk_ids.append(
                chunk_id
            )

            is_relevant = (
                chunk_id
                in relevant_chunk_ids
            )

            marker = (
                "RELEVANT"
                if is_relevant
                else "NOT RELEVANT"
            )

            print(
                f"\nRank {rank}"
            )

            print(
                f"  Chunk ID        : "
                f"{chunk_id}"
            )

            print(
                f"  RRF score       : "
                f"{result.get('rrf_score', 0.0):.6f}"
            )

            print(
                f"  Reranker score  : "
                f"{reranker_score:.4f}"
            )

            print(
                f"  Ground truth    : "
                f"{marker}"
            )

        # ----------------------------------------------------
        # Calculate metrics
        # ----------------------------------------------------

        metrics = calculate_metrics(
            ranked_chunk_ids,
            relevant_chunk_ids
        )

        print("\nMetrics:")

        print(
            f"  Hit@1       : "
            f"{'YES' if metrics['hit_at_1'] else 'NO'}"
        )

        print(
            f"  Hit@3       : "
            f"{'YES' if metrics['hit_at_3'] else 'NO'}"
        )

        print(
            f"  Hit@5       : "
            f"{'YES' if metrics['hit_at_5'] else 'NO'}"
        )

        print(
            f"  Precision@5 : "
            f"{metrics['precision_at_5']:.4f}"
        )

        print(
            f"  MRR         : "
            f"{metrics['mrr']:.4f}"
        )

        # ----------------------------------------------------
        # Accumulate
        # ----------------------------------------------------

        total_hit_at_1 += int(
            metrics["hit_at_1"]
        )

        total_hit_at_3 += int(
            metrics["hit_at_3"]
        )

        total_hit_at_5 += int(
            metrics["hit_at_5"]
        )

        total_precision_at_5 += (
            metrics["precision_at_5"]
        )

        total_mrr += metrics["mrr"]

    # ========================================================
    # OVERALL METRICS
    # ========================================================

    question_count = len(questions)

    if question_count == 0:

        print("\nNo questions found.")

        return

    average_hit_at_1 = (
        total_hit_at_1
        / question_count
    )

    average_hit_at_3 = (
        total_hit_at_3
        / question_count
    )

    average_hit_at_5 = (
        total_hit_at_5
        / question_count
    )

    average_precision_at_5 = (
        total_precision_at_5
        / question_count
    )

    average_mrr = (
        total_mrr
        / question_count
    )

    print("\n")
    print("=" * 70)
    print("OVERALL RERANKED RETRIEVAL METRICS")
    print("=" * 70)

    print(
        f"\nQuestions tested : "
        f"{question_count}"
    )

    print(
        "\nAfter Reranking:"
    )

    print(
        f"  Hit@1"
        f"        : "
        f"{average_hit_at_1 * 100:.2f}%"
    )

    print(
        f"  Hit@3"
        f"        : "
        f"{average_hit_at_3 * 100:.2f}%"
    )

    print(
        f"  Hit@5"
        f"        : "
        f"{average_hit_at_5 * 100:.2f}%"
    )

    print(
        f"  Precision@5"
        f" : "
        f"{average_precision_at_5 * 100:.2f}%"
    )

    print(
        f"  MRR"
        f"        : "
        f"{average_mrr:.4f}"
    )

    # ========================================================
    # COMPARISON
    # ========================================================

    print("\n")
    print("=" * 70)
    print("BEFORE vs AFTER RERANKING")
    print("=" * 70)

    print(
        "\n"
        "Metric          Before       After"
    )

    print("-" * 70)

    print(
        f"Hit@1           "
        f"80.00%        "
        f"{average_hit_at_1 * 100:.2f}%"
    )

    print(
        f"Hit@3           "
        f"100.00%       "
        f"{average_hit_at_3 * 100:.2f}%"
    )

    print(
        f"Hit@5           "
        f"100.00%       "
        f"{average_hit_at_5 * 100:.2f}%"
    )

    print(
        f"Precision@5     "
        f"60.00%        "
        f"{average_precision_at_5 * 100:.2f}%"
    )

    print(
        f"MRR             "
        f"0.9000        "
        f"{average_mrr:.4f}"
    )

    print("\n")
    print("=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)

    print(
        "\nImportant:"
    )

    print(
        "These metrics tell us whether "
        "reranking improved retrieval."
    )

    print(
        "They do NOT yet tell us whether "
        "the final LLM answer is grounded."
    )

    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()