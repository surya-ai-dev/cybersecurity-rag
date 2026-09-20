from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from bm25_retriever import load_documents, BM25Retriever
from rrf_fusion import reciprocal_rank_fusion


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"

COLLECTION_NAME = "cybersecurity_chunks"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

DENSE_TOP_K = 20
BM25_TOP_K = 20
RRF_TOP_K = 5


# ============================================================
# LOAD MODELS / DATABASE
# ============================================================

print("=" * 70)
print("RAG RETRIEVER")
print("=" * 70)

print("\nLoading BGE model...")

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL
)

print("BGE model loaded.")


print("\nLoading BM25 documents...")

documents = load_documents()

bm25 = BM25Retriever(documents)

print(f"Loaded {len(documents):,} documents/chunks.")


print("\nConnecting to Qdrant...")

client = QdrantClient(
    path=str(QDRANT_PATH)
)

print("Qdrant connected.")


# ============================================================
# DENSE RETRIEVAL
# ============================================================

def dense_retrieve(
    question: str,
    top_k: int = DENSE_TOP_K
):

    query_embedding = embedding_model.encode(
        question,
        normalize_embeddings=True
    )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding.tolist(),
        limit=top_k,
        with_payload=True
    ).points

    documents = []

    for point in results:

        payload = point.payload or {}

        chunk_id = payload.get("chunk_id")

        if chunk_id is None:
            continue

        documents.append(
    {
        "chunk_id": chunk_id,
        "text": payload.get("text", ""),
        "score": float(point.score),
        "metadata": {
            "document_id": payload.get(
                "document_id",
                "Unknown"
            ),
            "source_file": payload.get(
                "source_file",
                "Unknown"
            ),
            "section": payload.get(
                "section",
                "Unknown"
            )
        }
    }
)

    return documents


# ============================================================
# HYBRID RETRIEVAL
# ============================================================

def retrieve(
    question: str,
    top_k: int = RRF_TOP_K
):

    print("\nDense retrieval...")

    dense_results = dense_retrieve(
        question,
        DENSE_TOP_K
    )

    print(
        f"Dense results: {len(dense_results)}"
    )


    print("\nBM25 retrieval...")

    bm25_results = bm25.retrieve(
        question,
        BM25_TOP_K
    )

    print(
        f"BM25 results: {len(bm25_results)}"
    )


    print("\nRRF fusion...")

    fused_results = reciprocal_rank_fusion(
        [
            dense_results,
            bm25_results
        ],
        top_k=top_k
    )

    print(
        f"Final RRF results: {len(fused_results)}"
    )

    return fused_results


# ============================================================
# DISPLAY RESULTS
# ============================================================

def print_results(results):

    print("\n" + "=" * 70)
    print("RETRIEVAL RESULTS")
    print("=" * 70)

    for rank, result in enumerate(
        results,
        start=1
    ):

        print(
            f"\nRank {rank}"
        )

        print(
            f"Chunk ID : "
            f"{result.get('chunk_id')}"
        )

        print(
            f"RRF     : "
            f"{result.get('rrf_score', 0):.6f}"
        )

        text = result.get(
            "text",
            ""
        )

        print(
            f"Text    : "
            f"{text[:300]}..."
        )


# ============================================================
# TEST
# ============================================================

def main():

    question = input(
        "\nEnter cybersecurity question: "
    ).strip()

    if not question:
        print("Question cannot be empty.")
        return

    results = retrieve(question)

    print_results(results)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()