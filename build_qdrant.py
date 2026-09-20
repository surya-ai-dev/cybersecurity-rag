from pathlib import Path
import json
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)


# ============================================================
# CONFIG
# ============================================================

EMBEDDINGS_DIR = Path("data/embeddings_small")

QDRANT_DIR = Path("data/qdrant")

COLLECTION_NAME = "cybersecurity_chunks"

VECTOR_SIZE = 384

BATCH_SIZE = 256


# ============================================================
# LOAD EMBEDDINGS
# ============================================================

def load_embeddings():

    npy_files = sorted(
        EMBEDDINGS_DIR.glob("*.npy")
    )

    print(f"Found embedding files: {len(npy_files)}")

    all_embeddings = []
    all_metadata = []

    for npy_file in npy_files:

        json_file = npy_file.with_suffix(".json")

        if not json_file.exists():
            print(f"⚠️ Missing metadata: {json_file}")
            continue

        embeddings = np.load(npy_file)

        with open(
            json_file,
            "r",
            encoding="utf-8"
        ) as file:

            metadata = json.load(file)

        print(
            f"{npy_file.name}: "
            f"{embeddings.shape[0]} vectors"
        )

        all_embeddings.append(embeddings)
        all_metadata.extend(metadata)

    embeddings = np.vstack(all_embeddings)

    print()
    print(f"Total vectors : {len(embeddings):,}")
    print(f"Dimensions    : {embeddings.shape[1]}")
    print(f"Metadata      : {len(all_metadata):,}")

    return embeddings, all_metadata


# ============================================================
# CREATE QDRANT
# ============================================================

def create_qdrant():

    QDRANT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\nInitializing Qdrant...")

    client = QdrantClient(
        path=str(QDRANT_DIR)
    )

    print("✅ Qdrant initialized")

    return client


# ============================================================
# CREATE COLLECTION
# ============================================================

def create_collection(client):

    existing_collections = [
        collection.name
        for collection in client.get_collections().collections
    ]

    if COLLECTION_NAME in existing_collections:

        print(
            f"\nCollection '{COLLECTION_NAME}' "
            f"already exists."
        )

        return

    print(
        f"\nCreating collection: "
        f"{COLLECTION_NAME}"
    )

    client.create_collection(

        collection_name=COLLECTION_NAME,

        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE
        )
    )

    print("✅ Collection created")


# ============================================================
# INSERT VECTORS
# ============================================================

def insert_vectors(
    client,
    embeddings,
    metadata
):

    total = len(embeddings)

    print("\nInserting vectors...")
    print(f"Total vectors: {total:,}")
    print(f"Batch size: {BATCH_SIZE}")

    for start in range(
        0,
        total,
        BATCH_SIZE
    ):

        end = min(
            start + BATCH_SIZE,
            total
        )

        points = []

        for index in range(
            start,
            end
        ):

            payload = metadata[index].copy()

            point = PointStruct(

                id=index,

                vector=embeddings[index].tolist(),

                payload=payload
            )

            points.append(point)

        client.upsert(

            collection_name=COLLECTION_NAME,

            points=points
        )

        print(
            f"Inserted "
            f"{end:,}/{total:,}"
        )

    print("\n✅ All vectors inserted")


# ============================================================
# VERIFY
# ============================================================

def verify(client):

    info = client.get_collection(
        COLLECTION_NAME
    )

    print("\n")
    print("=" * 60)
    print("QDRANT VERIFICATION")
    print("=" * 60)

    print(
        f"Collection : {COLLECTION_NAME}"
    )

    print(
        f"Vectors    : "
        f"{info.points_count:,}"
    )

    print(
        f"Dimensions : {VECTOR_SIZE}"
    )

    print(
        f"Distance   : COSINE"
    )

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("CYBERSECURITY QDRANT VECTOR DATABASE")
    print("=" * 60)

    # Load existing embeddings
    embeddings, metadata = load_embeddings()

    # Safety checks
    if embeddings.shape[1] != VECTOR_SIZE:

        raise ValueError(
            f"Expected {VECTOR_SIZE} dimensions "
            f"but found {embeddings.shape[1]}"
        )

    if len(embeddings) != len(metadata):

        raise ValueError(
            "Embedding count and metadata count "
            "do not match."
        )

    # Start Qdrant
    client = create_qdrant()

    # Create collection
    create_collection(client)

    # Insert vectors
    insert_vectors(
        client,
        embeddings,
        metadata
    )

    # Verify
    verify(client)

    print("\n🎉 Qdrant setup complete!")


if __name__ == "__main__":
    main()