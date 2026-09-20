from pathlib import Path
import json
import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIG
# ============================================================

CHUNKS_DIR = Path("data/chunks")
OUTPUT_DIR = Path("data/embeddings")

MODEL_NAME = "BAAI/bge-m3"

# SAFE CPU SETTINGS
BATCH_SIZE = 4
CPU_THREADS = 4

# Set to None for full dataset
# Set to 20 for testing
TEST_LIMIT = 20


# ============================================================
# CPU CONFIGURATION
# ============================================================

torch.set_num_threads(CPU_THREADS)

print("=" * 70)
print("NIST BGE-M3 SAFE CPU EMBEDDING PIPELINE")
print("=" * 70)

print(f"PyTorch version : {torch.__version__}")
print(f"CPU threads     : {CPU_THREADS}")
print(f"Batch size      : {BATCH_SIZE}")
print("Device          : CPU")


# ============================================================
# LOAD CHUNK FILES
# ============================================================

def get_chunk_files():

    files = sorted(
        CHUNKS_DIR.rglob("*.json")
    )

    print(
        f"\nFound {len(files)} chunk files."
    )

    return files


# ============================================================
# LOAD ONE CHUNK FILE
# ============================================================

def load_chunk_file(file_path):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# EMBED ONE DOCUMENT
# ============================================================

def embed_document(
    model,
    file_path,
    document_index,
    total_documents
):

    chunks = load_chunk_file(file_path)

    if not chunks:

        print(
            f"⚠️ Empty file: {file_path}"
        )

        return 0, "empty"


    # --------------------------------------------------------
    # Output filenames
    # --------------------------------------------------------

    output_name = file_path.stem

    embeddings_path = (
        OUTPUT_DIR /
        f"{output_name}.npy"
    )

    metadata_path = (
        OUTPUT_DIR /
        f"{output_name}.json"
    )


    # --------------------------------------------------------
    # Resume support
    # --------------------------------------------------------

    if (
        embeddings_path.exists()
        and metadata_path.exists()
    ):

        print(
            f"\n[{document_index}/{total_documents}] "
            f"SKIPPING: {file_path.name}"
        )

        print(
            "Already embedded."
        )

        return 0, "skipped"


    print("\n" + "=" * 70)

    print(
        f"[{document_index}/{total_documents}] "
        f"Processing: {file_path.name}"
    )

    print(
        f"Chunks: {len(chunks):,}"
    )


    # --------------------------------------------------------
    # Prepare texts
    # --------------------------------------------------------

    texts = [
        chunk["text"]
        for chunk in chunks
    ]


    # --------------------------------------------------------
    # Generate embeddings
    # --------------------------------------------------------

    print("Generating embeddings...")

    embeddings = model.encode(

        texts,

        batch_size=BATCH_SIZE,

        normalize_embeddings=True,

        show_progress_bar=True,

        convert_to_numpy=True,

        device="cpu"
    )


    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    print(
        f"Embedding shape: {embeddings.shape}"
    )

    print(
        f"Embedding dtype: {embeddings.dtype}"
    )


    # --------------------------------------------------------
    # Save embeddings IMMEDIATELY
    # --------------------------------------------------------

    np.save(
        embeddings_path,
        embeddings.astype(
            np.float32
        )
    )


    # --------------------------------------------------------
    # Save metadata
    # --------------------------------------------------------

    metadata = []

    for index, chunk in enumerate(chunks):

        metadata.append({

            "embedding_index": index,

            "chunk_id": chunk.get(
                "chunk_id"
            ),

            "document_id": chunk.get(
                "document_id"
            ),

            "category": chunk.get(
                "category"
            ),

            "source_file": chunk.get(
                "source_file"
            ),

            "section": chunk.get(
                "section"
            ),

            "token_count": chunk.get(
                "token_count"
            ),

            "text": chunk.get(
                "text"
            )
        })


    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False
        )


    print(
        f"✅ Embeddings saved:"
    )

    print(
        f"   {embeddings_path}"
    )

    print(
        f"✅ Metadata saved:"
    )

    print(
        f"   {metadata_path}"
    )

    return len(chunks), "success"


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------------
    # Find chunk files
    # --------------------------------------------------------

    chunk_files = get_chunk_files()

    if not chunk_files:

        print(
            "❌ No chunk files found."
        )

        return


    # --------------------------------------------------------
    # TEST MODE
    # --------------------------------------------------------

    files_to_process = chunk_files

    if TEST_LIMIT is not None:

        files_to_process = chunk_files[:TEST_LIMIT]

        print(
            f"\n⚠️ TEST MODE"
        )

        print(
            f"Processing first "
            f"{len(files_to_process)} "
            f"documents only."
        )

    else:

        print(
            "\n🚀 FULL DATASET MODE"
        )


    # --------------------------------------------------------
    # Load model
    # --------------------------------------------------------

    print("\nLoading BGE-M3...")

    model = SentenceTransformer(
        MODEL_NAME,

        device="cpu"
    )

    print(
        "✅ BGE-M3 loaded successfully."
    )


    # --------------------------------------------------------
    # Process documents
    # --------------------------------------------------------

    total_chunks = 0

    successful = 0

    skipped = 0

    failed = 0


    total = len(files_to_process)


    for index, file_path in enumerate(
        files_to_process,
        start=1
    ):

        try:

            count, status = embed_document(

                model,

                file_path,

                index,

                total
            )


            total_chunks += count


            if status == "success":

                successful += 1

            elif status == "skipped":

                skipped += 1


        except Exception as error:

            failed += 1

            print(
                f"\n❌ Failed: {file_path.name}"
            )

            print(
                f"Error: {error}"
            )


    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print("\n")

    print("=" * 70)

    print("EMBEDDING RUN COMPLETE")

    print("=" * 70)

    print(
        f"Documents processed : {successful}"
    )

    print(
        f"Documents skipped   : {skipped}"
    )

    print(
        f"Documents failed    : {failed}"
    )

    print(
        f"Chunks processed    : {total_chunks:,}"
    )

    print(
        f"Output directory    : {OUTPUT_DIR}"
    )

    print("=" * 70)


if __name__ == "__main__":

    main()