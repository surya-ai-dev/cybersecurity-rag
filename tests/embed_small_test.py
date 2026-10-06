from pathlib import Path
import json
import time

from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_DIR = PROJECT_ROOT / "data" / "chunks"

MODEL_NAME = "BAAI/bge-small-en-v1.5"

TEST_CHUNKS = 10
BATCH_SIZE = 4


def load_test_chunks():

    files = sorted(CHUNKS_DIR.rglob("*.json"))

    chunks = []

    for file_path in files:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        chunks.extend(data)

        if len(chunks) >= TEST_CHUNKS:
            break

    return chunks[:TEST_CHUNKS]


def main():

    print("=" * 60)
    print("BGE-SMALL SAFE EMBEDDING TEST")
    print("=" * 60)

    print("\nLoading test chunks...")

    chunks = load_test_chunks()

    print(
        f"Test chunks: {len(chunks)}"
    )

    print("\nLoading model...")

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu"
    )

    print("Model loaded successfully.")

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    print("\nGenerating embeddings...")

    start = time.time()

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True
    )

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    print(
        f"Chunks embedded : {len(texts)}"
    )

    print(
        f"Embedding shape : {embeddings.shape}"
    )

    print(
        f"Dimensions      : {embeddings.shape[1]}"
    )

    print(
        f"Data type       : {embeddings.dtype}"
    )

    print(
        f"Time taken      : {elapsed:.2f} seconds"
    )

    print("\nFirst embedding:")
    print(embeddings[0][:10])

    print("\n✅ BGE-small test successful.")


if __name__ == "__main__":
    main()