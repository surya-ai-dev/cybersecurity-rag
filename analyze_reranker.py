import json
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient


# ============================================================
# CONFIG
# ============================================================

QDRANT_PATH = "data/qdrant"
COLLECTION_NAME = "cybersecurity_chunks"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

QUESTIONS_FILE = "evaluation_questions.json"
GROUND_TRUTH_FILE = "ground_truth.json"

VECTOR_TOP_K = 10
RERANK_TOP_K = 5


# ============================================================
# LOAD QUESTIONS
# ============================================================

def load_questions():

    with open(
        QUESTIONS_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


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
# RETRIEVE
# ============================================================

def retrieve_documents(
    client,
    model,
    question
):

    query_vector = model.encode(
        question,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector.tolist(),
        limit=VECTOR_TOP_K,
        with_payload=True
    ).points

    documents = []

    for result in results:

        payload = result.payload or {}

        documents.append(
            {
                "chunk_id": payload.get(
                    "chunk_id"
                ),

                "text": payload.get(
                    "text",
                    ""
                ),

                "similarity_score": float(
                    result.score
                )
            }
        )

    return documents


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

    scores = reranker.predict(
        pairs,
        show_progress_bar=False
    )

    ranked = []

    for document, score in zip(
        documents,
        scores
    ):

        ranked.append(
            {
                **document,
                "reranker_score": float(score)
            }
        )

    ranked.sort(
        key=lambda x: x[
            "reranker_score"
        ],
        reverse=True
    )

    return ranked[:RERANK_TOP_K]


# ============================================================
# CHECK RELEVANCE
# ============================================================

def is_relevant(
    chunk_id,
    relevant_chunks
):

    return chunk_id in relevant_chunks


# ============================================================
# ANALYZE ONE QUESTION
# ============================================================

def analyze_question(
    question_item,
    ground_truth,
    embedding_model,
    reranker,
    client
):

    question_id = question_item["id"]
    question = question_item["question"]

    relevant_chunks = set(
        ground_truth[question_id]
    )

    print("\n")
    print("=" * 70)
    print(question_id)
    print("=" * 70)

    print("\nQuestion:")
    print(question)

    # --------------------------------------------------------
    # VECTOR RETRIEVAL
    # --------------------------------------------------------

    vector_results = retrieve_documents(
        client,
        embedding_model,
        question
    )

    print("\nVECTOR TOP-10")
    print("-" * 70)

    for rank, document in enumerate(
        vector_results,
        start=1
    ):

        chunk_id = document["chunk_id"]

        relevant = is_relevant(
            chunk_id,
            relevant_chunks
        )

        status = (
            "RELEVANT"
            if relevant
            else "NOT RELEVANT"
        )

        print(
            f"{rank:2d}. "
            f"{chunk_id:<30} "
            f"score={document['similarity_score']:.4f} "
            f"{status}"
        )

    # --------------------------------------------------------
    # RERANK
    # --------------------------------------------------------

    reranked_results = rerank_documents(
        reranker,
        question,
        vector_results
    )

    print("\nRERANKED TOP-5")
    print("-" * 70)

    for rank, document in enumerate(
        reranked_results,
        start=1
    ):

        chunk_id = document["chunk_id"]

        relevant = is_relevant(
            chunk_id,
            relevant_chunks
        )

        status = (
            "RELEVANT"
            if relevant
            else "NOT RELEVANT"
        )

        print(
            f"{rank:2d}. "
            f"{chunk_id:<30} "
            f"vector={document['similarity_score']:.4f} "
            f"reranker={document['reranker_score']:.4f} "
            f"{status}"
        )

    # --------------------------------------------------------
    # DETECT PROBLEMS
    # --------------------------------------------------------

    vector_top1 = vector_results[0]

    reranker_top1 = reranked_results[0]

    print("\nANALYSIS")
    print("-" * 70)

    vector_top1_relevant = is_relevant(
        vector_top1["chunk_id"],
        relevant_chunks
    )

    reranker_top1_relevant = is_relevant(
        reranker_top1["chunk_id"],
        relevant_chunks
    )

    if (
        vector_top1_relevant
        and not reranker_top1_relevant
    ):

        print(
            "❌ RERANKER REGRESSION"
        )

        print(
            "Vector retrieval found a relevant "
            "chunk at rank 1, but reranking "
            "moved an irrelevant chunk to rank 1."
        )

    elif (
        not vector_top1_relevant
        and reranker_top1_relevant
    ):

        print(
            "✅ RERANKER IMPROVEMENT"
        )

        print(
            "Reranking moved a relevant chunk "
            "to rank 1."
        )

    elif (
        vector_top1_relevant
        and reranker_top1_relevant
    ):

        print(
            "➡️ NO CHANGE NEEDED AT TOP-1"
        )

        print(
            "Both methods selected a relevant "
            "chunk at rank 1."
        )

    else:

        print(
            "⚠️ BOTH METHODS MISSED"
        )

        print(
            "Neither vector retrieval nor "
            "reranking selected a relevant "
            "chunk at rank 1."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("RERANKER ERROR ANALYSIS")
    print("=" * 70)

    # --------------------------------------------------------
    # Load questions
    # --------------------------------------------------------

    print("\nLoading questions...")

    questions = load_questions()

    print(
        f"Loaded {len(questions)} questions."
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
        path=QDRANT_PATH
    )

    print("✅ Qdrant connected")

    # --------------------------------------------------------
    # Analyze every question
    # --------------------------------------------------------

    for question_item in questions:

        analyze_question(
            question_item,
            ground_truth,
            embedding_model,
            reranker,
            client
        )

    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("RERANKER ERROR ANALYSIS COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()