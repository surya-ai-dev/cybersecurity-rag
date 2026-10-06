from pathlib import Path
import json
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings_small"


def main():

    print("=" * 70)
    print("EMBEDDING VALIDATION")
    print("=" * 70)

    npy_files = sorted(
        EMBEDDINGS_DIR.glob("*.npy")
    )

    json_files = sorted(
        EMBEDDINGS_DIR.glob("*.json")
    )

    print(f"Embedding files : {len(npy_files)}")
    print(f"Metadata files  : {len(json_files)}")

    # --------------------------------------------------------
    # File count check
    # --------------------------------------------------------

    embedding_names = {
        file.stem
        for file in npy_files
    }

    metadata_names = {
        file.stem
        for file in json_files
    }

    missing_metadata = (
        embedding_names - metadata_names
    )

    missing_embeddings = (
        metadata_names - embedding_names
    )

    print("\nFILE CONSISTENCY")
    print("-" * 70)

    if not missing_metadata:
        print("✅ Every .npy has metadata")

    else:
        print(
            "❌ Missing metadata:",
            missing_metadata
        )

    if not missing_embeddings:
        print("✅ Every metadata file has .npy")

    else:
        print(
            "❌ Missing embeddings:",
            missing_embeddings
        )

    # --------------------------------------------------------
    # Inspect embeddings
    # --------------------------------------------------------

    total_vectors = 0
    dimensions = set()

    print("\nCHECKING EMBEDDINGS")
    print("-" * 70)

    for npy_file in npy_files:

        embeddings = np.load(
            npy_file,
            mmap_mode="r"
        )

        total_vectors += embeddings.shape[0]

        dimensions.add(
            embeddings.shape[1]
        )

        if embeddings.dtype != np.float32:

            print(
                f"⚠️ {npy_file.name}: "
                f"dtype={embeddings.dtype}"
            )

    print(
        f"Total vectors : {total_vectors:,}"
    )

    print(
        f"Dimensions    : {dimensions}"
    )

    # --------------------------------------------------------
    # Validate metadata
    # --------------------------------------------------------

    total_metadata = 0

    print("\nCHECKING METADATA")
    print("-" * 70)

    for json_file in json_files:

        with open(
            json_file,
            "r",
            encoding="utf-8"
        ) as file:

            metadata = json.load(file)

        total_metadata += len(metadata)

    print(
        f"Metadata records : {total_metadata:,}"
    )

    # --------------------------------------------------------
    # Final comparison
    # --------------------------------------------------------

    print("\nFINAL CHECK")
    print("=" * 70)

    if total_vectors == total_metadata:

        print(
            "✅ Vector count == metadata count"
        )

    else:

        print(
            "❌ VECTOR/METADATA COUNT MISMATCH"
        )

        print(
            f"Vectors  : {total_vectors}"
        )

        print(
            f"Metadata : {total_metadata}"
        )

    if dimensions == {384}:

        print(
            "✅ All embeddings are 384-dimensional"
        )

    else:

        print(
            "⚠️ Unexpected dimensions:",
            dimensions
        )

    print("=" * 70)


if __name__ == "__main__":
    main()