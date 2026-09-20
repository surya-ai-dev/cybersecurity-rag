"""
BM25 Retriever
--------------
Keyword-based retrieval for the Cybersecurity RAG system.

Input:
    User question

Output:
    Top-K relevant chunks with:
        - chunk_id
        - BM25 score
        - text
        - metadata
"""

from pathlib import Path
import json
import re

from rank_bm25 import BM25Okapi


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

# We will update this path if your actual metadata location differs.
METADATA_DIR = PROJECT_ROOT / "data"

TOP_K = 20


# ============================================================
# TOKENIZATION
# ============================================================

def tokenize(text: str) -> list[str]:
    """
    Simple BM25 tokenizer.

    Example:
        "Public cloud security risks"
        ->
        ["public", "cloud", "security", "risks"]
    """

    text = text.lower()

    # Keep words and numbers
    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text)

    return tokens


# ============================================================
# LOAD DOCUMENTS
# ============================================================

def load_documents():
    """
    Find and load chunk metadata from the project.

    Expected document format:

    [
        {
            "chunk_id": "...",
            "text": "..."
        }
    ]
    """

    json_files = list(METADATA_DIR.rglob("*.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No JSON metadata files found inside: {METADATA_DIR}"
        )

    documents = []

    for file_path in json_files:

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        except Exception:
            continue

        # Case 1:
        # JSON contains a list of chunks
        if isinstance(data, list):

            for item in data:

                if not isinstance(item, dict):
                    continue

                chunk_id = (
                    item.get("chunk_id")
                    or item.get("id")
                    or item.get("chunkId")
                )

                text = (
                    item.get("text")
                    or item.get("content")
                    or item.get("chunk")
                )

                if chunk_id and text:
                    documents.append(
                        {
                            "chunk_id": str(chunk_id),
                            "text": str(text),
                            "metadata": item,
                        }
                    )

        # Case 2:
        # JSON contains {"chunks": [...]}
        elif isinstance(data, dict):

            chunks = data.get("chunks")

            if isinstance(chunks, list):

                for item in chunks:

                    if not isinstance(item, dict):
                        continue

                    chunk_id = (
                        item.get("chunk_id")
                        or item.get("id")
                        or item.get("chunkId")
                    )

                    text = (
                        item.get("text")
                        or item.get("content")
                        or item.get("chunk")
                    )

                    if chunk_id and text:
                        documents.append(
                            {
                                "chunk_id": str(chunk_id),
                                "text": str(text),
                                "metadata": item,
                            }
                        )

    # Remove duplicate chunk IDs
    unique_documents = {}

    for doc in documents:
        unique_documents[doc["chunk_id"]] = doc

    documents = list(unique_documents.values())

    if not documents:
        raise RuntimeError(
            "JSON files were found, but no valid chunks were loaded."
        )

    return documents


# ============================================================
# BM25 RETRIEVER
# ============================================================

class BM25Retriever:

    def __init__(self, documents):

        self.documents = documents

        print(f"Building BM25 index for {len(documents):,} chunks...")

        tokenized_documents = [
            tokenize(doc["text"])
            for doc in documents
        ]

        self.bm25 = BM25Okapi(tokenized_documents)

        print("✅ BM25 index built")

    def retrieve(self, query: str, top_k: int = TOP_K):

        query_tokens = tokenize(query)

        scores = self.bm25.get_scores(query_tokens)

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )

        results = []

        for index in ranked_indices[:top_k]:

            document = self.documents[index]

            results.append(
                {
                    "chunk_id": document["chunk_id"],
                    "score": float(scores[index]),
                    "text": document["text"],
                    "metadata": document["metadata"],
                }
            )

        return results


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("BM25 RETRIEVER TEST")
    print("=" * 70)

    print("\nLoading documents...")

    documents = load_documents()

    print(f"Loaded {len(documents):,} chunks")

    retriever = BM25Retriever(documents)

    question = input(
        "\nEnter your question:\n> "
    ).strip()

    if not question:
        print("❌ Question cannot be empty")
        return

    print("\n" + "=" * 70)
    print("BM25 RESULTS")
    print("=" * 70)

    results = retriever.retrieve(
        question,
        top_k=TOP_K,
    )

    for rank, result in enumerate(results, start=1):

        print("\n" + "-" * 70)

        print(f"Rank      : {rank}")
        print(f"Chunk ID   : {result['chunk_id']}")
        print(f"BM25 score : {result['score']:.4f}")

        print("\nText:")
        print(result["text"][:500])

    print("\n" + "=" * 70)
    print("BM25 TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()