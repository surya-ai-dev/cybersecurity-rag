from pathlib import Path
import json
import gc
import time

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHUNKS_DIR = PROJECT_ROOT / "data" / "chunks"
OUTPUT_DIR = PROJECT_ROOT / "data" / "embeddings_small"

MODEL_NAME = "BAAI/bge-small-en-v1.5"

BATCH_SIZE = 2
CPU_THREADS = 2

# Set to None for ALL documents
TEST_LIMIT = None


# ============================================================
# CPU SETTINGS
# ============================================================

torch.set_num_threads(CPU_THREADS)

print("=" * 70)
print("BGE-SMALL RESUME-SAFE EMBEDDING PIPELINE")
print("=" * 70)

print(f"PyTorch version : {torch.__version__}")
print(f"CPU threads     : {CPU_THREADS}")
print(f"Batch size      : {BATCH_SIZE}")
print(f"Model           : {MODEL_NAME}")
print(f"Device          : CPU")


# ============================================================
# LOAD DOCUMENT LIST
# ============================================================

def get_chunk_files():

    files = sorted(
        CHUNKS_DIR.rglob("*.json")
    )

    print(f"\nFound {len(files)} chunk files.")

    return files


# ============================================================
# LOAD CHUNKS
# ============================================================

def load_chunks(file_path):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results(
    document_id,
    embeddings,
    chunks
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Save embeddings
    # --------------------------------------------------------

    embeddings_path = (
        OUTPUT_DIR /
        f"{document_id}.npy"
    )

    np.save(
        embeddings_path,
        embeddings
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

    metadata_path = (
        OUTPUT_DIR /
        f"{document_id}.json"
    )

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

    return embeddings_path, metadata_path


# ============================================================
# MAIN
# ============================================================

def main():

    chunk_files = get_chunk_files()

    if not chunk_files:

        print("❌ No chunk files found.")

        return

    # --------------------------------------------------------
    # Test limit
    # --------------------------------------------------------

    if TEST_LIMIT is not None:

        chunk_files = chunk_files[:TEST_LIMIT]

        print(
            f"⚠️ TEST MODE: "
            f"processing {len(chunk_files)} documents."
        )

    else:

        print(
            f"FULL MODE: "
            f"processing {len(chunk_files)} documents."
        )

    # --------------------------------------------------------
    # Load model
    # --------------------------------------------------------

    print("\nLoading BGE-small...")

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu"
    )

    print("✅ Model loaded successfully.")

    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    completed = 0
    skipped = 0
    failed = 0
    total_chunks = 0

    start_all = time.time()

    # --------------------------------------------------------
    # Process documents one at a time
    # --------------------------------------------------------

    for index, file_path in enumerate(
        chunk_files,
        start=1
    ):

        document_id = file_path.stem

        embeddings_path = (
            OUTPUT_DIR /
            f"{document_id}.npy"
        )

        metadata_path = (
            OUTPUT_DIR /
            f"{document_id}.json"
        )

        print("\n" + "=" * 70)

        print(
            f"[{index}/{len(chunk_files)}] "
            f"Processing: {file_path.name}"
        )

        # ----------------------------------------------------
        # Resume support
        # ----------------------------------------------------

        if (
            embeddings_path.exists()
            and metadata_path.exists()
        ):

            print(
                "⏭️ Already completed. Skipping."
            )

            skipped += 1

            continue

        try:

            # ------------------------------------------------
            # Load chunks
            # ------------------------------------------------

            chunks = load_chunks(
                file_path
            )

            print(
                f"Chunks: {len(chunks):,}"
            )

            if not chunks:

                print(
                    "⚠️ Empty document. Skipping."
                )

                skipped += 1

                continue

            texts = [
                chunk["text"]
                for chunk in chunks
            ]

            # ------------------------------------------------
            # Generate embeddings
            # ------------------------------------------------

            print(
                "Generating embeddings..."
            )

            start = time.time()

            embeddings = model.encode(

                texts,

                batch_size=BATCH_SIZE,

                normalize_embeddings=True,

                show_progress_bar=True,

                convert_to_numpy=True
            )

            elapsed = time.time() - start

            print(
                f"Embedding shape: "
                f"{embeddings.shape}"
            )

            print(
                f"Time: {elapsed:.2f} seconds"
            )

            # ------------------------------------------------
            # Save immediately
            # ------------------------------------------------

            emb_path, meta_path = save_results(

                document_id,

                embeddings,

                chunks
            )

            print(
                f"✅ Embeddings saved: "
                f"{emb_path}"
            )

            print(
                f"✅ Metadata saved: "
                f"{meta_path}"
            )

            completed += 1
            total_chunks += len(chunks)

            # ------------------------------------------------
            # Free memory
            # ------------------------------------------------

            del embeddings
            del texts
            del chunks

            gc.collect()

        except Exception as error:

            failed += 1

            print(
                f"❌ Failed: {file_path.name}"
            )

            print(
                f"Error: {error}"
            )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    total_time = (
        time.time() - start_all
    )

    print("\n")
    print("=" * 70)
    print("EMBEDDING PIPELINE COMPLETE")
    print("=" * 70)

    print(
        f"Completed documents : {completed}"
    )

    print(
        f"Skipped documents   : {skipped}"
    )

    print(
        f"Failed documents    : {failed}"
    )

    print(
        f"New chunks embedded : {total_chunks:,}"
    )

    print(
        f"Time                : "
        f"{total_time / 60:.2f} minutes"
    )

    print(
        f"Output              : "
        f"{OUTPUT_DIR}"
    )

    print("=" * 70)


if __name__ == "__main__":

    main()