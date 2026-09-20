from pathlib import Path

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIG
# ============================================================

QDRANT_PATH = Path("data/qdrant")

COLLECTION_NAME = "cybersecurity_chunks"

MODEL_NAME = "BAAI/bge-small-en-v1.5"

TOP_K = 5


# ============================================================
# LOAD MODEL
# ============================================================

print("=" * 70)
print("QDRANT VECTOR SEARCH TEST")
print("=" * 70)

print("\nLoading BGE-small...")

model = SentenceTransformer(MODEL_NAME)

print("✅ Model loaded")


# ============================================================
# CONNECT TO QDRANT
# ============================================================

print("\nConnecting to Qdrant...")

client = QdrantClient(
    path=str(QDRANT_PATH)
)

print("✅ Qdrant connected")


# ============================================================
# CHECK COLLECTION
# ============================================================

collection_info = client.get_collection(
    COLLECTION_NAME
)

print("\nCollection:")
print(f"Name    : {COLLECTION_NAME}")
print(
    f"Vectors : "
    f"{collection_info.points_count:,}"
)


# ============================================================
# USER QUERY
# ============================================================

query = input(
    "\nEnter cybersecurity question: "
)

print("\nQuery:")
print(query)


# ============================================================
# CREATE QUERY EMBEDDING
# ============================================================

print("\nGenerating query embedding...")

query_embedding = model.encode(
    query,
    normalize_embeddings=True,
    convert_to_numpy=True
)

print("✅ Query embedding generated")

print(
    f"Dimension: {query_embedding.shape[0]}"
)


# ============================================================
# SEARCH QDRANT
# ============================================================

print("\nSearching Qdrant...")

results = client.query_points(
    collection_name=COLLECTION_NAME,
    query=query_embedding.tolist(),
    limit=TOP_K,
    with_payload=True
).points


# ============================================================
# DISPLAY RESULTS
# ============================================================

print("\n")
print("=" * 70)
print("SEARCH RESULTS")
print("=" * 70)

for rank, result in enumerate(results, start=1):

    payload = result.payload or {}

    print("\n" + "-" * 70)

    print(f"Rank       : {rank}")
    print(f"Score      : {result.score:.4f}")

    print(
        f"Chunk ID   : "
        f"{payload.get('chunk_id', 'N/A')}"
    )

    print(
        f"Document   : "
        f"{payload.get('document_id', 'N/A')}"
    )

    print(
        f"Category   : "
        f"{payload.get('category', 'N/A')}"
    )

    print(
        f"Section    : "
        f"{payload.get('section', 'N/A')}"
    )

    text = payload.get("text", "")

    print("\nText:")
    print(text[:1000])


# ============================================================
# COMPLETE
# ============================================================

print("\n")
print("=" * 70)
print("VECTOR SEARCH COMPLETE")
print("=" * 70)