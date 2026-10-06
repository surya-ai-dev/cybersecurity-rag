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


# ============================================================
# CONFIG
# ============================================================

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

RERANKER_MODEL_NAME = (
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

COLLECTION_NAME = "cybersecurity_chunks"

TOP_K_VECTOR = 10
TOP_K_FINAL = 5

vector_weight=0.8,
reranker_weight=0.2

EVALUATION_FILE = PROJECT_ROOT / "data" / "evaluation" / "evaluation_questions.json"
GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "evaluation" / "ground_truth.json"


# ============================================================
# LOAD JSON
# ============================================================

def load_json(filename):

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {filename}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# LOAD EVALUATION QUESTIONS
# ============================================================

def load_questions():

    data = load_json(EVALUATION_FILE)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        if "questions" in data:
            return data["questions"]

    raise ValueError(
        "Invalid evaluation_questions.json format"
    )


# ============================================================
# LOAD GROUND TRUTH
# ============================================================

def load_ground_truth():

    data = load_json(GROUND_TRUTH_FILE)

    return data


# ============================================================
# EXTRACT QUESTION
# ============================================================

def get_question(item):

    if isinstance(item, str):
        return item

    if "question" in item:
        return item["question"]

    if "query" in item:
        return item["query"]

    raise ValueError(
        f"Cannot find question in: {item}"
    )


# ============================================================
# EXTRACT GROUND TRUTH IDS
# ============================================================

def get_relevant_ids(
    ground_truth,
    question,
    question_index
):
    
    # Handle dictionary format:
    # {
    #   "Q1": ["chunk1", "chunk2"],
    #   "Q2": ["chunk3", "chunk4"]
    # }
    if isinstance(ground_truth, dict):
        q_key = f"Q{question_index + 1}"

        if q_key in ground_truth:
            return ground_truth[q_key]

        # Also support question text as a key
        if question in ground_truth:
            return ground_truth[question]

        return []

    # --------------------------------------------------------
    # Format 1:
    #
    # {
    #   "questions": [
    #       {
    #           "question": "...",
    #           "relevant_chunks": [...]
    #       }
    #   ]
    # }
    # --------------------------------------------------------

    if isinstance(ground_truth, dict):

        if "questions" in ground_truth:

            items = ground_truth["questions"]

            for item in items:

                if not isinstance(item, dict):
                    continue

                q = (
                    item.get("question")
                    or item.get("query")
                )

                if q == question:

                    return (
                        item.get("relevant_chunks")
                        or item.get("relevant_chunk_ids")
                        or item.get("relevant")
                        or []
                    )

        # ----------------------------------------------------
        # Format 2:
        #
        # {
        #   "question": [...]
        # }
        # ----------------------------------------------------

        if question in ground_truth:

            value = ground_truth[question]

            if isinstance(value, list):
                return value

            if isinstance(value, dict):

                return (
                    value.get("relevant_chunks")
                    or value.get("relevant_chunk_ids")
                    or value.get("relevant")
                    or []
                )

    # --------------------------------------------------------
    # Format 3:
    #
    # [
    #   {
    #       "question": "...",
    #       "relevant_chunks": [...]
    #   }
    # ]
    # --------------------------------------------------------

    if isinstance(ground_truth, list):

        for item in ground_truth:

            if not isinstance(item, dict):
                continue

            q = (
                item.get("question")
                or item.get("query")
            )

            if q == question:

                return (
                    item.get("relevant_chunks")
                    or item.get("relevant_chunk_ids")
                    or item.get("relevant")
                    or []
                )

        # Fallback by position

        if question_index < len(ground_truth):

            item = ground_truth[question_index]

            if isinstance(item, dict):

                return (
                    item.get("relevant_chunks")
                    or item.get("relevant_chunk_ids")
                    or item.get("relevant")
                    or []
                )

    return []


# ============================================================
# CREATE EMBEDDING
# ============================================================

def create_query_embedding(
    model,
    question
):

    embedding = model.encode(
        question,
        normalize_embeddings=True
    )

    return embedding.tolist()


# ============================================================
# VECTOR SEARCH
# ============================================================

def vector_search(
    client,
    embedding,
    top_k
):

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        limit=top_k,
        with_payload=True
    )

    points = results.points

    documents = []

    for point in points:

        payload = point.payload or {}

        chunk_id = (
            payload.get("chunk_id")
            or payload.get("id")
            or str(point.id)
        )

        text = (
            payload.get("text")
            or payload.get("content")
            or ""
        )

        documents.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "score": float(point.score),
                "payload": payload
            }
        )

    return documents


# ============================================================
# NORMALIZE SCORES
# ============================================================

def min_max_normalize(scores):

    if not scores:
        return []

    minimum = min(scores)
    maximum = max(scores)

    if maximum == minimum:

        return [
            1.0
            for _ in scores
        ]

    return [
        (score - minimum)
        / (maximum - minimum)

        for score in scores
    ]


# ============================================================
# RERANK
# ============================================================

def rerank_documents(
    reranker,
    question,
    documents
):

    pairs = [
        (
            question,
            document["text"]
        )

        for document in documents
    ]

    scores = reranker.predict(pairs)

    results = []

    for document, score in zip(
        documents,
        scores
    ):

        results.append(
            {
                **document,
                "reranker_score":
                    float(score)
            }
        )

    results.sort(
        key=lambda x:
            x["reranker_score"],
        reverse=True
    )

    return results


# ============================================================
# HYBRID RERANK
# ============================================================

def hybrid_rerank(
    documents,
    vector_weight,
    reranker_weight
):

    if not documents:
        return []

    vector_scores = [
        document["score"]
        for document in documents
    ]

    reranker_scores = [
        document["reranker_score"]
        for document in documents
    ]

    normalized_vector = min_max_normalize(
        vector_scores
    )

    normalized_reranker = min_max_normalize(
        reranker_scores
    )

    results = []

    for (
        document,
        vector_norm,
        reranker_norm
    ) in zip(
        documents,
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

                "normalized_vector_score":
                    vector_norm,

                "normalized_reranker_score":
                    reranker_norm,

                "hybrid_score":
                    hybrid_score
            }
        )

    results.sort(
        key=lambda x:
            x["hybrid_score"],
        reverse=True
    )

    return results


# ============================================================
# CHECK RELEVANCE
# ============================================================

def is_relevant(
    chunk_id,
    relevant_ids
):

    return chunk_id in relevant_ids


# ============================================================
# CALCULATE METRICS
# ============================================================

def calculate_metrics(
    ranked_results,
    relevant_ids
):

    if not ranked_results:
        return {
            "hit1": 0,
            "hit3": 0,
            "hit5": 0,
            "precision5": 0,
            "mrr": 0
        }

    relevant = [
        is_relevant(
            result["chunk_id"],
            relevant_ids
        )

        for result in ranked_results
    ]

    # --------------------------------------------------------
    # Hit@1
    # --------------------------------------------------------

    hit1 = (
        1
        if relevant[:1].count(True) > 0
        else 0
    )

    # --------------------------------------------------------
    # Hit@3
    # --------------------------------------------------------

    hit3 = (
        1
        if any(relevant[:3])
        else 0
    )

    # --------------------------------------------------------
    # Hit@5
    # --------------------------------------------------------

    hit5 = (
        1
        if any(relevant[:5])
        else 0
    )

    # --------------------------------------------------------
    # Precision@5
    # --------------------------------------------------------

    top5 = relevant[:5]

    precision5 = (
        sum(top5)
        / len(top5)
        if top5
        else 0
    )

    # --------------------------------------------------------
    # MRR
    # --------------------------------------------------------

    mrr = 0

    for rank, value in enumerate(
        relevant,
        start=1
    ):

        if value:

            mrr = 1 / rank

            break

    return {
        "hit1": hit1,
        "hit3": hit3,
        "hit5": hit5,
        "precision5": precision5,
        "mrr": mrr
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("HYBRID RERANKED RETRIEVAL EVALUATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Questions
    # --------------------------------------------------------

    print("\nLoading evaluation questions...")

    questions = load_questions()

    print(
        f"Loaded {len(questions)} questions."
    )

    # --------------------------------------------------------
    # Ground truth
    # --------------------------------------------------------

    print("\nLoading ground truth...")

    ground_truth = load_ground_truth()

    print(
        "Ground truth loaded."
    )

    # --------------------------------------------------------
    # Embedding model
    # --------------------------------------------------------

    print("\nLoading BGE-small...")

    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME
    )

    print("✅ BGE-small loaded")

    # --------------------------------------------------------
    # Reranker
    # --------------------------------------------------------

    print("\nLoading reranker...")

    reranker = CrossEncoder(
        RERANKER_MODEL_NAME
    )

    print("✅ Reranker loaded")

    # --------------------------------------------------------
    # Qdrant
    # --------------------------------------------------------

    print("\nConnecting to Qdrant...")

    client = QdrantClient(
        path=str(PROJECT_ROOT / "data" / "qdrant")
    )
    print("✅ Qdrant connected")

    # --------------------------------------------------------
    # Metric storage
    # --------------------------------------------------------

    vector_metrics = []

    reranker_metrics = []

    hybrid_metrics = []

    # ========================================================
    # EVALUATION LOOP
    # ========================================================

    for index, item in enumerate(
        questions
    ):

        question = get_question(item)

        relevant_ids = get_relevant_ids(
            ground_truth,
            question,
            index
        )

        print("\n")
        print("=" * 70)
        print(f"Q{index + 1}")
        print("=" * 70)

        print("\nQuestion:")
        print(question)

        print("\nGround-truth relevant chunks:")

        for chunk_id in relevant_ids:

            print(
                f"  {chunk_id}"
            )

        # ----------------------------------------------------
        # VECTOR RETRIEVAL
        # ----------------------------------------------------

        embedding = create_query_embedding(
            embedding_model,
            question
        )

        vector_results = vector_search(
            client,
            embedding,
            TOP_K_VECTOR
        )

        print("\nVector retrieval → Top-10")

        print(
            f"Retrieved {len(vector_results)} candidates."
        )

        # ----------------------------------------------------
        # VECTOR METRICS
        # ----------------------------------------------------

        vector_top5 = vector_results[
            :TOP_K_FINAL
        ]

        vector_result_metrics = calculate_metrics(
            vector_top5,
            relevant_ids
        )

        vector_metrics.append(
            vector_result_metrics
        )

        # ----------------------------------------------------
        # RERANK
        # ----------------------------------------------------

        reranked = rerank_documents(
            reranker,
            question,
            vector_results
        )

        reranked_top5 = reranked[
            :TOP_K_FINAL
        ]

        reranker_result_metrics = calculate_metrics(
            reranked_top5,
            relevant_ids
        )

        reranker_metrics.append(
            reranker_result_metrics
        )

        # ----------------------------------------------------
        # HYBRID
        # ----------------------------------------------------
        VECTOR_WEIGHT = 0.8
        RERANKER_WEIGHT = 0.2

        hybrid_results = hybrid_rerank(
            reranked,
            VECTOR_WEIGHT,
            RERANKER_WEIGHT
        )

        hybrid_top5 = hybrid_results[
            :TOP_K_FINAL
        ]

        hybrid_result_metrics = calculate_metrics(
            hybrid_top5,
            relevant_ids
        )

        hybrid_metrics.append(
            hybrid_result_metrics
        )

        # ----------------------------------------------------
        # DISPLAY RESULTS
        # ----------------------------------------------------

        print("\n")
        print("-" * 70)
        print("HYBRID TOP-5")
        print("-" * 70)

        for rank, result in enumerate(
            hybrid_top5,
            start=1
        ):

            relevant = is_relevant(
                result["chunk_id"],
                relevant_ids
            )

            status = (
                "RELEVANT"
                if relevant
                else "NOT RELEVANT"
            )

            print(
                f"{rank}. "
                f"{result['chunk_id']:<35} "
                f"vector="
                f"{result['score']:.4f} "
                f"reranker="
                f"{result['reranker_score']:.4f} "
                f"hybrid="
                f"{result['hybrid_score']:.4f} "
                f"{status}"
            )

        print("\nMetrics:")

        print(
            f"  Hit@1       : "
            f"{'YES' if hybrid_result_metrics['hit1'] else 'NO'}"
        )

        print(
            f"  Hit@3       : "
            f"{'YES' if hybrid_result_metrics['hit3'] else 'NO'}"
        )

        print(
            f"  Hit@5       : "
            f"{'YES' if hybrid_result_metrics['hit5'] else 'NO'}"
        )

        print(
            f"  Precision@5 : "
            f"{hybrid_result_metrics['precision5']:.4f}"
        )

        print(
            f"  MRR         : "
            f"{hybrid_result_metrics['mrr']:.4f}"
        )

    # ========================================================
    # OVERALL METRICS
    # ========================================================

    def average(
        metrics,
        key
    ):

        if not metrics:
            return 0

        return sum(
            item[key]
            for item in metrics
        ) / len(metrics)

    # --------------------------------------------------------
    # Vector
    # --------------------------------------------------------

    vector_overall = {
        "hit1":
            average(vector_metrics, "hit1"),

        "hit3":
            average(vector_metrics, "hit3"),

        "hit5":
            average(vector_metrics, "hit5"),

        "precision5":
            average(vector_metrics, "precision5"),

        "mrr":
            average(vector_metrics, "mrr")
    }

    # --------------------------------------------------------
    # Reranker
    # --------------------------------------------------------

    reranker_overall = {
        "hit1":
            average(reranker_metrics, "hit1"),

        "hit3":
            average(reranker_metrics, "hit3"),

        "hit5":
            average(reranker_metrics, "hit5"),

        "precision5":
            average(
                reranker_metrics,
                "precision5"
            ),

        "mrr":
            average(reranker_metrics, "mrr")
    }

    # --------------------------------------------------------
    # Hybrid
    # --------------------------------------------------------

    hybrid_overall = {
        "hit1":
            average(hybrid_metrics, "hit1"),

        "hit3":
            average(hybrid_metrics, "hit3"),

        "hit5":
            average(hybrid_metrics, "hit5"),

        "precision5":
            average(
                hybrid_metrics,
                "precision5"
            ),

        "mrr":
            average(hybrid_metrics, "mrr")
    }

    # ========================================================
    # DISPLAY OVERALL
    # ========================================================

    print("\n\n")
    print("=" * 70)
    print("OVERALL RETRIEVAL COMPARISON")
    print("=" * 70)

    print("\nMetric          Vector      Reranker      Hybrid")
    print("-" * 70)

    print(
        f"Hit@1           "
        f"{vector_overall['hit1'] * 100:6.2f}%     "
        f"{reranker_overall['hit1'] * 100:6.2f}%       "
        f"{hybrid_overall['hit1'] * 100:6.2f}%"
    )

    print(
        f"Hit@3           "
        f"{vector_overall['hit3'] * 100:6.2f}%     "
        f"{reranker_overall['hit3'] * 100:6.2f}%       "
        f"{hybrid_overall['hit3'] * 100:6.2f}%"
    )

    print(
        f"Hit@5           "
        f"{vector_overall['hit5'] * 100:6.2f}%     "
        f"{reranker_overall['hit5'] * 100:6.2f}%       "
        f"{hybrid_overall['hit5'] * 100:6.2f}%"
    )

    print(
        f"Precision@5     "
        f"{vector_overall['precision5'] * 100:6.2f}%     "
        f"{reranker_overall['precision5'] * 100:6.2f}%       "
        f"{hybrid_overall['precision5'] * 100:6.2f}%"
    )

    print(
        f"MRR             "
        f"{vector_overall['mrr']:.4f}      "
        f"{reranker_overall['mrr']:.4f}        "
        f"{hybrid_overall['mrr']:.4f}"
    )

    # ========================================================
    # BEFORE VS AFTER
    # ========================================================

    print("\n")
    print("=" * 70)
    print("HYBRID IMPROVEMENT")
    print("=" * 70)

    precision_before = (
        vector_overall["precision5"]
        * 100
    )

    precision_after = (
        hybrid_overall["precision5"]
        * 100
    )

    improvement = (
        precision_after
        - precision_before
    )

    print(
        f"\nVector Precision@5 : "
        f"{precision_before:.2f}%"
    )

    print(
        f"Hybrid Precision@5 : "
        f"{precision_after:.2f}%"
    )

    print(
        f"Change             : "
        f"{improvement:+.2f}%"
    )

    if improvement > 0:

        print(
            "\n✅ HYBRID IMPROVED RETRIEVAL"
        )

    elif improvement == 0:

        print(
            "\n➡️ HYBRID DID NOT CHANGE PRECISION"
        )

    else:

        print(
            "\n❌ HYBRID MADE RETRIEVAL WORSE"
        )

    # ========================================================
    # CONFIG
    # ========================================================

    print("\n")
    print("=" * 70)
    print("HYBRID CONFIGURATION")
    print("=" * 70)

    print(
        f"\nVector weight   : "
        f"{VECTOR_WEIGHT}"
    )

    print(
        f"Reranker weight : "
        f"{RERANKER_WEIGHT}"
    )

    print(
        f"\nEmbedding model : "
        f"{EMBEDDING_MODEL_NAME}"
    )

    print(
        f"Reranker model  : "
        f"{RERANKER_MODEL_NAME}"
    )

    print("\n")
    print("=" * 70)
    print("HYBRID EVALUATION COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()