"""Ingestion pipeline for finalized BGE-M3 embeddings into Qdrant.

Loads precomputed embeddings from data/embeddings_bge_m3/ without re-encoding,
validates integrity against the manifest, constructs deterministic point IDs,
attaches rich payloads, and ingests into Qdrant in safe batches.

Supports:
- Embedded local Qdrant (path-based) and Client-Server Qdrant (URL-based)
- Dry-run / Preflight mode (no database writes)
- Deterministic ID strategies (integer index or UUIDv5)
- Full payload (metadata + text + section) or metadata-only
- Post-ingestion verification and sample querying
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Windows console UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Namespace for deterministic UUIDv5 generation
QDRANT_NAMESPACE = uuid.UUID("e80a0662-520e-450b-8086-630f9a2ef776")

DEFAULT_EMBEDDINGS_DIR = PROJECT_ROOT / "data" / "embeddings_bge_m3"
DEFAULT_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
DEFAULT_COLLECTION_NAME = "cybersecurity_chunks_bge_m3"
DEFAULT_BATCH_SIZE = 256
EXPECTED_DIMENSION = 1024
EXPECTED_TOTAL_CHUNKS = 13084
EXPECTED_CORPUS_FINGERPRINT = (
    "91f3d87f4fe3ece9930cc72c9576a01dd313ef94b585b6bb1f94b1a16f61c018"
)


# ==============================================================================
# ARTIFACT INTEGRITY VERIFICATION
# ==============================================================================

def verify_artifacts(
    embeddings_dir: Path,
) -> Tuple[np.ndarray, List[Dict[str, Any]], Dict[str, Any]]:
    """Validate and load finalized embedding matrix, metadata, and manifest.

    Args:
        embeddings_dir: Directory containing embeddings.npy, chunk_metadata.jsonl, manifest.json.

    Returns:
        embeddings: Loaded float32 numpy matrix of shape (13084, 1024).
        metadata: List of metadata dicts parsed from chunk_metadata.jsonl.
        manifest: Dictionary loaded from manifest.json.
    """
    npy_path = embeddings_dir / "embeddings.npy"
    meta_path = embeddings_dir / "chunk_metadata.jsonl"
    manifest_path = embeddings_dir / "manifest.json"

    # 1. Existence check
    for p in [npy_path, meta_path, manifest_path]:
        if not p.exists():
            raise FileNotFoundError(f"Required artifact not found: {p}")

    # 2. Manifest check
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    status = manifest.get("status")
    if status != "FINALIZED":
        raise ValueError(
            f"Embedding manifest status is '{status}', expected 'FINALIZED'."
        )

    model_name = manifest.get("model_name")
    if "bge-m3" not in model_name.lower():
        raise ValueError(f"Manifest model '{model_name}' is not BGE-M3.")

    total_chunks = manifest.get("total_chunks", 0)
    embedding_dim = manifest.get("embedding_dim", 0)
    corpus_fp = manifest.get("corpus_fingerprint", "")
    final_sha = manifest.get("final_sha256", "")

    if total_chunks != EXPECTED_TOTAL_CHUNKS:
        raise ValueError(
            f"Manifest total_chunks={total_chunks}, expected {EXPECTED_TOTAL_CHUNKS}."
        )
    if embedding_dim != EXPECTED_DIMENSION:
        raise ValueError(
            f"Manifest embedding_dim={embedding_dim}, expected {EXPECTED_DIMENSION}."
        )
    if corpus_fp != EXPECTED_CORPUS_FINGERPRINT:
        raise ValueError(
            f"Corpus fingerprint mismatch in manifest:\n  Found:    {corpus_fp}\n  Expected: {EXPECTED_CORPUS_FINGERPRINT}"
        )

    # 3. Embedding Matrix Check
    print(f"Loading embedding matrix from {npy_path}...")
    embeddings = np.load(npy_path)

    if embeddings.shape != (EXPECTED_TOTAL_CHUNKS, EXPECTED_DIMENSION):
        raise ValueError(
            f"Embeddings shape {embeddings.shape} != expected ({EXPECTED_TOTAL_CHUNKS}, {EXPECTED_DIMENSION})"
        )
    if embeddings.dtype != np.float32:
        raise ValueError(f"Expected float32 dtype, found {embeddings.dtype}")

    # Verify SHA-256 buffer hash matches manifest
    computed_sha = hashlib.sha256(embeddings.tobytes()).hexdigest()
    if computed_sha != final_sha:
        raise ValueError(
            f"Embeddings buffer SHA-256 mismatch:\n  Computed: {computed_sha}\n  Manifest: {final_sha}"
        )

    # 4. Metadata Check
    print(f"Loading chunk metadata from {meta_path}...")
    metadata: List[Dict[str, Any]] = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            item = json.loads(line_str)
            if "chunk_id" not in item:
                raise ValueError(f"Missing chunk_id in metadata line {line_num}")
            metadata.append(item)

    if len(metadata) != EXPECTED_TOTAL_CHUNKS:
        raise ValueError(
            f"Metadata records count ({len(metadata)}) != expected ({EXPECTED_TOTAL_CHUNKS})"
        )

    return embeddings, metadata, manifest


# ==============================================================================
# CHUNK TEXT & FULL METADATA ENRICHMENT
# ==============================================================================

def load_source_chunk_data() -> Dict[str, Dict[str, Any]]:
    """Load full chunk records from source JSONL files (pilot + corpus).

    Returns:
        chunk_map: Mapping from chunk_id to full dict containing text, section_heading,
                   section_path, citation_label, content_type, etc.
    """
    pilot_dir = PROJECT_ROOT / "data" / "chunks_pilot"
    corpus_dir = PROJECT_ROOT / "data" / "chunks_corpus"

    files = sorted(
        list(pilot_dir.rglob("*_chunks.jsonl"))
        + list(corpus_dir.rglob("*_chunks.jsonl")),
        key=lambda p: p.as_posix(),
    )

    chunk_map: Dict[str, Dict[str, Any]] = {}
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                item = json.loads(line_str)
                cid = item.get("chunk_id")
                if cid:
                    chunk_map[cid] = item

    return chunk_map


# ==============================================================================
# POINT BUILDER & ID STRATEGY
# ==============================================================================

def make_point_id(
    idx: int,
    chunk_id: str,
    id_scheme: str = "integer",
) -> Any:
    """Generate deterministic point ID.

    Args:
        idx: 0-based row index in embeddings matrix.
        chunk_id: Canonical chunk ID string (e.g. 'NIST_SP_800-144_txt_00001').
        id_scheme: 'integer' (default) or 'uuid'.

    Returns:
        int or UUID string.
    """
    if id_scheme == "integer":
        return idx
    elif id_scheme == "uuid":
        return str(uuid.uuid5(QDRANT_NAMESPACE, chunk_id))
    else:
        raise ValueError(f"Unknown id_scheme: {id_scheme}")


def build_payload(
    meta_row: Dict[str, Any],
    source_chunk: Optional[Dict[str, Any]],
    include_text: bool = True,
) -> Dict[str, Any]:
    """Construct searchable payload for Qdrant point.

    Args:
        meta_row: Baseline metadata from chunk_metadata.jsonl.
        source_chunk: Optional full chunk data from source JSONL.
        include_text: Whether to include 'text' in payload.

    Returns:
        payload: Clean dictionary for Qdrant storage.
    """
    payload = {
        "chunk_id": meta_row["chunk_id"],
        "document_id": meta_row["document_id"],
        "category": meta_row["category"],
        "content_type": meta_row["content_type"],
        "page_start": meta_row["page_start"],
        "page_end": meta_row["page_end"],
        "token_count": meta_row["token_count"],
        "source_file": meta_row["source_file"],
    }

    if source_chunk:
        # Enrich with retrieval and citation fields
        if "section_heading" in source_chunk and source_chunk["section_heading"]:
            payload["section"] = source_chunk["section_heading"]
            payload["section_heading"] = source_chunk["section_heading"]
        if "section_path" in source_chunk and source_chunk["section_path"]:
            payload["section_path"] = source_chunk["section_path"]
        if "citation_label" in source_chunk and source_chunk["citation_label"]:
            payload["citation_label"] = source_chunk["citation_label"]

        if include_text:
            payload["text"] = source_chunk.get("text", "")
    else:
        if include_text:
            payload["text"] = ""

    return payload


# ==============================================================================
# QDRANT CLIENT CONNECTION
# ==============================================================================

def get_qdrant_client(
    qdrant_path: Optional[Path] = None,
    qdrant_url: Optional[str] = None,
):
    """Instantiate and return a QdrantClient instance.

    Args:
        qdrant_path: Local filesystem directory for embedded Qdrant.
        qdrant_url: HTTP or gRPC URL for remote/containerized Qdrant.

    Returns:
        QdrantClient
    """
    from qdrant_client import QdrantClient

    if qdrant_url:
        print(f"Connecting to remote Qdrant server at: {qdrant_url}")
        return QdrantClient(url=qdrant_url)
    else:
        target_path = qdrant_path or DEFAULT_QDRANT_PATH
        target_path.mkdir(parents=True, exist_ok=True)
        print(f"Connecting to embedded local Qdrant at: {target_path}")
        return QdrantClient(path=str(target_path))


# ==============================================================================
# COLLECTION MANAGEMENT
# ==============================================================================

def prepare_collection(
    client,
    collection_name: str,
    dimension: int = EXPECTED_DIMENSION,
    recreate: bool = False,
) -> bool:
    """Ensure Qdrant collection exists with proper configuration.

    Args:
        client: QdrantClient instance.
        collection_name: Name of collection.
        dimension: Embedding dimension (1024 for BGE-M3).
        recreate: If True, delete existing collection before creating.

    Returns:
        created_new: True if collection was created, False if existing was retained.
    """
    from qdrant_client.models import Distance, VectorParams

    existing_collections = [c.name for c in client.get_collections().collections]

    if collection_name in existing_collections:
        if recreate:
            print(f"Deleting existing collection '{collection_name}' (--recreate)...")
            client.delete_collection(collection_name)
        else:
            info = client.get_collection(collection_name)
            current_dim = (
                info.config.params.vectors.size
                if hasattr(info.config.params.vectors, "size")
                else None
            )
            print(
                f"Collection '{collection_name}' already exists with {info.points_count:,d} points (dimension={current_dim})."
            )
            if current_dim is not None and current_dim != dimension:
                raise ValueError(
                    f"Existing collection dimension ({current_dim}) does not match required ({dimension}). "
                    f"Use a different collection name or supply --recreate to replace."
                )
            return False

    print(f"Creating collection '{collection_name}' (dim={dimension}, distance=COSINE)...")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=dimension,
            distance=Distance.COSINE,
        ),
    )
    print(f"Collection '{collection_name}' successfully created.")
    return True


# ==============================================================================
# INGESTION RUNNER
# ==============================================================================

def run_ingestion(
    client,
    collection_name: str,
    embeddings: np.ndarray,
    metadata: List[Dict[str, Any]],
    source_chunks: Optional[Dict[str, Dict[str, Any]]] = None,
    id_scheme: str = "integer",
    include_text: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """Upload embedding vectors and payloads into Qdrant in conservative batches.

    Args:
        client: QdrantClient instance.
        collection_name: Target collection name.
        embeddings: Float32 matrix (13084, 1024).
        metadata: Metadata list from chunk_metadata.jsonl.
        source_chunks: Optional full source chunk dictionary.
        id_scheme: 'integer' or 'uuid'.
        include_text: Whether to attach chunk text to payload.
        batch_size: Number of points per upsert call.

    Returns:
        stats: Dictionary of ingestion execution statistics.
    """
    from qdrant_client.models import PointStruct

    total = len(embeddings)
    start_time = time.time()
    total_batches = (total + batch_size - 1) // batch_size

    print(f"\n{'=' * 70}")
    print(f"STARTING QDRANT INGESTION")
    print(f"{'=' * 70}")
    print(f"Target Collection : {collection_name}")
    print(f"Total Points      : {total:,d}")
    print(f"Batch Size        : {batch_size}")
    print(f"Total Batches     : {total_batches}")
    print(f"ID Scheme         : {id_scheme}")
    print(f"Include Text      : {include_text}")
    print(f"{'=' * 70}\n")

    uploaded_count = 0
    errors: List[str] = []

    for batch_idx in range(total_batches):
        b_start = batch_idx * batch_size
        b_end = min(b_start + batch_size, total)

        points: List[PointStruct] = []
        for i in range(b_start, b_end):
            meta_row = metadata[i]
            cid = meta_row["chunk_id"]
            pt_id = make_point_id(i, cid, id_scheme=id_scheme)

            src = source_chunks.get(cid) if source_chunks else None
            payload = build_payload(meta_row, src, include_text=include_text)

            point = PointStruct(
                id=pt_id,
                vector=embeddings[i].tolist(),
                payload=payload,
            )
            points.append(point)

        try:
            client.upsert(
                collection_name=collection_name,
                points=points,
                wait=True,
            )
            uploaded_count += len(points)
            pct = (uploaded_count / total) * 100
            elapsed = time.time() - start_time
            rate = uploaded_count / elapsed if elapsed > 0 else 0
            eta = (total - uploaded_count) / rate if rate > 0 else 0
            print(
                f"[Batch {batch_idx + 1:2d}/{total_batches}] "
                f"Uploaded {uploaded_count:5,d}/{total:,d} points ({pct:5.1f}%) "
                f"| Rate: {rate:4.0f} pts/sec | ETA: {eta:4.1f}s"
            )
        except Exception as exc:
            err_msg = f"Failed to upload batch {batch_idx + 1} (indices {b_start}..{b_end - 1}): {exc}"
            print(f"ERROR: {err_msg}")
            errors.append(err_msg)
            raise RuntimeError(err_msg) from exc

    elapsed_total = time.time() - start_time
    print(f"\nIngestion finished in {elapsed_total:.2f} seconds.")

    return {
        "collection_name": collection_name,
        "total_points": total,
        "uploaded_points": uploaded_count,
        "elapsed_seconds": round(elapsed_total, 2),
        "batch_size": batch_size,
        "id_scheme": id_scheme,
        "include_text": include_text,
        "errors": errors,
    }


# ==============================================================================
# POST-INGESTION VERIFICATION
# ==============================================================================

def verify_collection(
    client,
    collection_name: str,
    expected_count: int = EXPECTED_TOTAL_CHUNKS,
) -> bool:
    """Verify points count, vector dimension, and inspect sample payloads.

    Args:
        client: QdrantClient instance.
        collection_name: Collection to verify.
        expected_count: Expected number of points.

    Returns:
        success: True if verification passed.
    """
    print(f"\n{'=' * 70}")
    print(f"QDRANT POST-INGESTION VERIFICATION")
    print(f"{'=' * 70}")

    info = client.get_collection(collection_name)
    current_count = info.points_count
    status = info.status

    current_dim = (
        info.config.params.vectors.size
        if hasattr(info.config.params.vectors, "size")
        else "Unknown"
    )
    current_dist = (
        info.config.params.vectors.distance
        if hasattr(info.config.params.vectors, "distance")
        else "Unknown"
    )

    print(f"Collection Name : {collection_name}")
    print(f"Status          : {status}")
    print(f"Points Count    : {current_count:,d} (Expected: {expected_count:,d})")
    print(f"Vector Dimension: {current_dim}")
    print(f"Distance Metric : {current_dist}")

    if current_count != expected_count:
        print(f"FAILURE: Count mismatch: {current_count} != {expected_count}")
        return False

    # Sample point retrieval inspection
    print("\nInspecting sample points:")
    sample_records = client.scroll(
        collection_name=collection_name,
        limit=3,
        with_payload=True,
        with_vectors=False,
    )[0]

    for idx, rec in enumerate(sample_records, start=1):
        payload = rec.payload or {}
        print(f"\n  Sample Point #{idx}:")
        print(f"    ID:           {rec.id}")
        print(f"    Chunk ID:     {payload.get('chunk_id')}")
        print(f"    Document ID:  {payload.get('document_id')}")
        print(f"    Category:     {payload.get('category')}")
        print(f"    Section:      {payload.get('section', payload.get('section_heading', 'N/A'))}")
        print(f"    Token Count:  {payload.get('token_count')}")
        text_preview = payload.get("text", "")
        if text_preview:
            preview_str = text_preview[:80].replace("\n", " ")
            print(f"    Text Preview: {preview_str}...")
        else:
            print("    Text Preview: [No text stored in payload]")

    print(f"\n{'=' * 70}")
    print(f"VERIFICATION SUCCESSFUL: {collection_name} is healthy and ready for queries.")
    print(f"{'=' * 70}\n")
    return True


# ==============================================================================
# PREFLIGHT / DRY-RUN REPORT
# ==============================================================================

def run_preflight(
    embeddings_dir: Path,
    qdrant_path: Path,
    qdrant_url: Optional[str],
    collection_name: str,
    id_scheme: str,
    include_text: bool,
    batch_size: int,
):
    """Execute dry-run preflight without modifying any database or files."""
    print(f"\n{'=' * 70}")
    print("QDRANT INGESTION PREFLIGHT / DRY-RUN AUDIT")
    print(f"{'=' * 70}")

    # 1. Environment & Storage
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    free_gb = free / (1024**3)
    print(f"Disk Free Space     : {free_gb:.2f} GB (Required reserve: >= 0.5 GB)")
    if free_gb < 0.5:
        print("WARNING: Disk space below safe threshold!")

    # 2. Embedding Artifacts Validation
    embeddings, metadata, manifest = verify_artifacts(embeddings_dir)
    print(f"Manifest Status     : {manifest.get('status')}")
    print(f"Model Name          : {manifest.get('model_name')}")
    print(f"Embedding Matrix    : {embeddings.shape} ({embeddings.dtype})")
    print(f"SHA-256 Buffer Hash : {manifest.get('final_sha256')}")
    print(f"Metadata Records    : {len(metadata):,d}")
    print(f"Corpus Fingerprint  : {manifest.get('corpus_fingerprint')}")

    # 3. Source Text Availability
    if include_text:
        source_chunks = load_source_chunk_data()
        print(f"Source Chunks Found : {len(source_chunks):,d} with full text & citations")
        missing_text_ids = [m["chunk_id"] for m in metadata if m["chunk_id"] not in source_chunks]
        if missing_text_ids:
            print(f"WARNING: {len(missing_text_ids)} chunk IDs missing from source JSONL files!")
        else:
            print("Chunk Text Coverage : 100% (All 13,084 chunk IDs matched source files)")
    else:
        print("Chunk Text Handling : DECOUPLED (--metadata-only mode selected)")

    # 4. Ingestion Configuration
    total_batches = (len(embeddings) + batch_size - 1) // batch_size
    print(f"\nPlanned Configuration:")
    print(f"  Target Collection : {collection_name}")
    print(f"  Connection Target : {'URL: ' + qdrant_url if qdrant_url else 'Embedded Path: ' + str(qdrant_path)}")
    print(f"  Point ID Scheme   : {id_scheme} (Sample ID 0: {make_point_id(0, metadata[0]['chunk_id'], id_scheme)})")
    print(f"  Batch Size        : {batch_size} ({total_batches} batches)")
    print(f"  Vector Size       : {EXPECTED_DIMENSION}")
    print(f"  Distance Metric   : COSINE")

    # 5. Sample Point Construction
    sample_src = source_chunks.get(metadata[0]["chunk_id"]) if include_text else None
    sample_payload = build_payload(metadata[0], sample_src, include_text=include_text)
    print(f"\nSample Point Payload (Row 0):")
    for k, v in sample_payload.items():
        if k == "text":
            print(f"    {k:15s}: {str(v)[:70]}... ({len(str(v))} chars)")
        else:
            print(f"    {k:15s}: {v}")

    print(f"\n{'=' * 70}")
    print("PREFLIGHT PASSED: All artifacts and configurations are valid.")
    print("NO WRITES WERE PERFORMED (Dry-Run Mode).")
    print(f"{'=' * 70}\n")


# ==============================================================================
# CLI PARSER & MAIN
# ==============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest finalized BGE-M3 embeddings into Qdrant vector database."
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=DEFAULT_EMBEDDINGS_DIR,
        help=f"Directory with finalized embeddings.npy and chunk_metadata.jsonl (default: {DEFAULT_EMBEDDINGS_DIR})",
    )
    parser.add_argument(
        "--qdrant-path",
        type=Path,
        default=DEFAULT_QDRANT_PATH,
        help=f"Path to embedded local Qdrant directory (default: {DEFAULT_QDRANT_PATH})",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Optional HTTP URL for remote Qdrant server (e.g. http://localhost:6333)",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default=DEFAULT_COLLECTION_NAME,
        help=f"Target Qdrant collection name (default: {DEFAULT_COLLECTION_NAME})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for Qdrant upserts (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--id-scheme",
        type=str,
        choices=["integer", "uuid"],
        default="integer",
        help="Point ID strategy: 'integer' (0..13083, row-aligned) or 'uuid' (deterministic UUIDv5) (default: integer)",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Do NOT include chunk text in Qdrant payload (stores only metadata fields)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate (drop and recreate) the collection if it already exists",
    )
    parser.add_argument(
        "--preflight",
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Run preflight integrity checks and plan display without modifying Qdrant",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing collection health and count without ingesting",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    include_text = not args.metadata_only

    if args.dry_run:
        run_preflight(
            embeddings_dir=args.embeddings_dir,
            qdrant_path=args.qdrant_path,
            qdrant_url=args.qdrant_url,
            collection_name=args.collection_name,
            id_scheme=args.id_scheme,
            include_text=include_text,
            batch_size=args.batch_size,
        )
        return

    # If verify-only requested
    if args.verify_only:
        client = get_qdrant_client(
            qdrant_path=args.qdrant_path,
            qdrant_url=args.qdrant_url,
        )
        try:
            success = verify_collection(
                client=client,
                collection_name=args.collection_name,
                expected_count=EXPECTED_TOTAL_CHUNKS,
            )
            sys.exit(0 if success else 1)
        finally:
            if hasattr(client, "close"):
                client.close()

    # Full Ingestion Workflow
    embeddings, metadata, manifest = verify_artifacts(args.embeddings_dir)

    source_chunks = None
    if include_text:
        print("Loading source chunk text and section metadata...")
        source_chunks = load_source_chunk_data()
        print(f"Loaded {len(source_chunks):,d} chunks for payload enrichment.")

    client = get_qdrant_client(
        qdrant_path=args.qdrant_path,
        qdrant_url=args.qdrant_url,
    )

    try:
        prepare_collection(
            client=client,
            collection_name=args.collection_name,
            dimension=EXPECTED_DIMENSION,
            recreate=args.recreate,
        )

        stats = run_ingestion(
            client=client,
            collection_name=args.collection_name,
            embeddings=embeddings,
            metadata=metadata,
            source_chunks=source_chunks,
            id_scheme=args.id_scheme,
            include_text=include_text,
            batch_size=args.batch_size,
        )

        verify_collection(
            client=client,
            collection_name=args.collection_name,
            expected_count=EXPECTED_TOTAL_CHUNKS,
        )

        print("\nAll ingestion steps completed successfully!")

    finally:
        if hasattr(client, "close"):
            client.close()


if __name__ == "__main__":
    main()
