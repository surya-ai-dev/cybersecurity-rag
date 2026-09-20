from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from bm25_retriever import load_documents, BM25Retriever
from rrf_fusion import reciprocal_rank_fusion


client = QdrantClient(path="data/qdrant")

model = SentenceTransformer("BAAI/bge-small-en-v1.5")

documents = load_documents()
bm25 = BM25Retriever(documents)
question = "How can malware on a client device threaten cloud services?"# Dense retrieval
query_vector = model.encode(
    question,
    normalize_embeddings=True,
    convert_to_numpy=True
)

dense_results = client.query_points(
    collection_name="cybersecurity_chunks",
    query=query_vector.tolist(),
    limit=20,
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


# BM25 retrieval
bm25_results = bm25.retrieve(
    question,
    20
)


# RRF fusion
fused_results = reciprocal_rank_fusion(
    [dense_documents, bm25_results],
    top_k=20
)


print("\n" + "=" * 80)
print("Q6 HYBRID RETRIEVAL")
print("=" * 80)

print("\nQuestion:")
print(question)

print("\nTop 20 RRF Candidates:\n")


for i, result in enumerate(fused_results, start=1):

    print(f"{i}. {result.get('chunk_id')}")
    print(f"RRF Score: {result.get('rrf_score', 0.0):.6f}")
    print(result.get("text", "")[:700])
    print("-" * 80)