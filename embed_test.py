from pathlib import Path
import json
from sentence_transformers import SentenceTransformer


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

CHUNKS_DIR = Path("data/chunks")
MODEL_NAME = "BAAI/bge-m3"

TEST_CHUNKS = 10


# --------------------------------------------------
# FIND CHUNKS
# --------------------------------------------------

def load_test_chunks():

    chunk_files = list(CHUNKS_DIR.rglob("*.json"))

    print(f"Found {len(chunk_files)} chunk files.")

    if not chunk_files:
        raise FileNotFoundError(
            "No chunk JSON files found in data/chunks/"
        )

    texts = []

    for file_path in chunk_files:

        with open(file_path, "r", encoding="utf-8") as file:
            chunks = json.load(file)

        for chunk in chunks:

            text = chunk.get("text", "").strip()

            if text:
                texts.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "text": text
                })

            if len(texts) >= TEST_CHUNKS:
                return texts

    return texts


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    print("=" * 60)
    print("BGE-M3 EMBEDDING TEST")
    print("=" * 60)

    print("\nLoading test chunks...")

    chunks = load_test_chunks()

    print(f"Test chunks loaded: {len(chunks)}")

    print("\nLoading embedding model...")
    print(f"Model: {MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME)

    print("✅ Model loaded successfully")

    # Extract text
    texts = [chunk["text"] for chunk in chunks]

    print("\nGenerating embeddings...")

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    print("\n" + "=" * 60)
    print("EMBEDDING TEST COMPLETE")
    print("=" * 60)

    print(f"Chunks embedded       : {len(texts)}")
    print(f"Embedding shape       : {embeddings.shape}")
    print(f"Embedding dimensions  : {embeddings.shape[1]}")
    print(f"Embedding data type   : {embeddings.dtype}")

    print("\nFirst chunk:")
    print(f"Chunk ID: {chunks[0]['chunk_id']}")
    print(f"Text preview: {chunks[0]['text'][:200]}...")

    print("\nFirst embedding preview:")
    print(embeddings[0][:10])

    print("\n✅ BGE-M3 embedding pipeline is working.")


if __name__ == "__main__":
    main()