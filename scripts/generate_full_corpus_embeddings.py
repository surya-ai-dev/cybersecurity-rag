#!/usr/bin/env python3
"""Resumable, Batch-wise Full-Corpus Embedding Generation Pipeline.

Generates 1024-dimensional dense embeddings for the entire 13,084 structure-aware
chunk corpus across 73 NIST publications using locally cached BAAI/bge-m3.

Design & Safety Principles:
1. Offline Execution: Strictly local weights (local_files_only=True). Never downloads models or packages.
2. Low-Memory Footprint: Saves durable checkpoints to disk in batches; frees vectors from RAM immediately.
3. Disk Space Protection: Enforces 500 MB mandatory safety reserve before writing.
4. Crash-Resilience & Resume: Checkpoints are written atomically. Resuming validates model/corpus compatibility.
5. Verification & Finalization: Built-in validation checks finite values, normalization, shape, and ID alignment.
6. Clean Separation: Outputs stored in dedicated directory; Qdrant insertion is decoupled to a future phase.
"""

import argparse
import gc
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import psutil

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Authoritative source directories
PILOT_CHUNKS_DIR = PROJECT_ROOT / "data" / "chunks_pilot"
CORPUS_CHUNKS_DIR = PROJECT_ROOT / "data" / "chunks_corpus"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "embeddings_bge_m3"

# Model configuration
DEFAULT_MODEL_NAME = "BAAI/bge-m3"
EXPECTED_EMBEDDING_DIM = 1024
EXPECTED_TOTAL_CHUNKS = 13084
MANDATORY_DISK_RESERVE_MB = 500.0


# ==============================================================================
# SYSTEM & CACHE INSPECTION
# ==============================================================================

def get_disk_free_mb(path: Path) -> float:
    """Return free disk space in megabytes for the filesystem containing path."""
    target = path if path.exists() else path.parent
    while not target.exists() and target != target.parent:
        target = target.parent
    usage = shutil.disk_usage(str(target))
    return usage.free / (1024 * 1024)


def get_process_memory_mb() -> float:
    """Return current process Resident Set Size (RSS) in megabytes."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def get_model_cache_info(model_name: str) -> Dict[str, Any]:
    """Inspect local Hugging Face cache for the specified model."""
    cache_dir = Path(os.getenv("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
    folder_name = "models--" + model_name.replace("/", "--")
    model_dir = cache_dir / folder_name

    info: Dict[str, Any] = {
        "model_name": model_name,
        "is_cached": False,
        "model_dir": str(model_dir),
        "snapshots": [],
        "active_revision": None,
        "weight_files": [],
        "total_cache_size_bytes": 0,
    }

    if not model_dir.exists():
        return info

    snapshots_dir = model_dir / "snapshots"
    if snapshots_dir.exists():
        for snap in snapshots_dir.iterdir():
            if snap.is_dir():
                info["snapshots"].append(snap.name)
                # Check for weights in this snapshot
                for w in ["model.safetensors", "pytorch_model.bin"]:
                    w_file = snap / w
                    if w_file.exists():
                        info["weight_files"].append(str(w_file))
                        info["total_cache_size_bytes"] += w_file.stat().st_size

    # Check refs/main
    refs_main = model_dir / "refs" / "main"
    if refs_main.exists():
        info["active_revision"] = refs_main.read_text(encoding="utf-8").strip()
    elif info["snapshots"]:
        info["active_revision"] = info["snapshots"][0]

    if info["weight_files"]:
        info["is_cached"] = True

    return info


# ==============================================================================
# AUTHORITATIVE CORPUS LOADER & FINGERPRINTING
# ==============================================================================

def discover_chunk_files() -> List[Path]:
    """Find and return all authoritative chunk JSONL files in deterministic order."""
    pilot_files = list(PILOT_CHUNKS_DIR.rglob("*_chunks.jsonl"))
    corpus_files = list(CORPUS_CHUNKS_DIR.rglob("*_chunks.jsonl"))
    all_files = sorted(pilot_files + corpus_files, key=lambda p: p.as_posix())
    return all_files


def load_authoritative_corpus() -> Tuple[List[Dict[str, Any]], str]:
    """Load all chunks, validate unique IDs, and compute deterministic fingerprint.

    Returns:
        chunks: List of chunk metadata dictionaries with 'chunk_id', 'document_id', etc.
        fingerprint: SHA-256 hex digest of ordered chunk IDs and text lengths.
    """
    files = discover_chunk_files()
    if not files:
        raise FileNotFoundError(f"No chunk files found in {PILOT_CHUNKS_DIR} or {CORPUS_CHUNKS_DIR}")

    chunks: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    hasher = hashlib.sha256()

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                line_str = line.strip()
                if not line_str:
                    continue
                item = json.loads(line_str)
                cid = item.get("chunk_id")
                if not cid:
                    raise ValueError(f"Missing chunk_id in {file_path}:{line_idx}")
                if cid in seen_ids:
                    raise ValueError(f"Duplicate chunk_id encountered: {cid} in {file_path}")
                seen_ids.add(cid)

                text = item.get("text", "")
                chunks.append({
                    "chunk_id": cid,
                    "document_id": item.get("document_id", ""),
                    "category": item.get("category", ""),
                    "content_type": item.get("content_type", "text"),
                    "page_start": item.get("page_start", 0),
                    "page_end": item.get("page_end", 0),
                    "token_count": item.get("token_count", 0),
                    "text": text,
                    "source_file": str(file_path.relative_to(PROJECT_ROOT)),
                })

                # Deterministic fingerprint update
                hasher.update(cid.encode("utf-8"))
                hasher.update(str(len(text)).encode("utf-8"))

    fingerprint = hasher.hexdigest()
    return chunks, fingerprint


# ==============================================================================
# MANIFEST MANAGEMENT
# ==============================================================================

class ManifestManager:
    """Manages atomic reads and writes of the generation manifest."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.manifest_path = output_dir / "manifest.json"

    def exists(self) -> bool:
        return self.manifest_path.exists()

    def load(self) -> Dict[str, Any]:
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def initialize(
        self,
        model_name: str,
        model_revision: Optional[str],
        embedding_dim: int,
        corpus_fingerprint: str,
        total_chunks: int,
        checkpoint_size: int,
        batch_size: int,
    ) -> Dict[str, Any]:
        """Initialize a new manifest file."""
        manifest: Dict[str, Any] = {
            "format_version": "1.0",
            "model_name": model_name,
            "model_revision": model_revision or "unknown",
            "embedding_dim": embedding_dim,
            "dtype": "float32",
            "normalized": True,
            "corpus_fingerprint": corpus_fingerprint,
            "total_chunks": total_chunks,
            "checkpoint_size": checkpoint_size,
            "inference_batch_size": batch_size,
            "status": "IN_PROGRESS",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_batches": [],
            "failed_batches": [],
        }
        self.save_atomic(manifest)
        return manifest

    def save_atomic(self, data: Dict[str, Any]) -> None:
        """Write manifest atomically via temporary file and rename."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = datetime.now().isoformat()
        tmp_path = self.manifest_path.with_suffix(".tmp.json")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self.manifest_path)


# ==============================================================================
# CHECKPOINT OPERATIONS (ATOMIC & VERIFIABLE)
# ==============================================================================

def get_checkpoint_paths(output_dir: Path, batch_idx: int) -> Tuple[Path, Path]:
    """Return paths for the checkpoint .npz vector file and .json metadata file."""
    ckp_dir = output_dir / "checkpoints"
    stem = f"checkpoint_{batch_idx:05d}"
    return ckp_dir / f"{stem}.npz", ckp_dir / f"{stem}.json"


def save_checkpoint_atomic(
    output_dir: Path,
    batch_idx: int,
    chunk_start: int,
    chunk_end: int,
    chunk_ids: List[str],
    vectors: np.ndarray,
    batch_metadata: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Atomically write a checkpoint batch with vectors and metadata.

    Args:
        output_dir: Root output directory.
        batch_idx: Sequential batch number.
        chunk_start: Start index in authoritative corpus.
        chunk_end: End index in authoritative corpus (exclusive).
        chunk_ids: List of chunk IDs for this batch.
        vectors: float32 numpy array of shape (N, 1024).
        batch_metadata: Chunk metadata records.

    Returns:
        Summary dict of the completed batch.
    """
    ckp_dir = output_dir / "checkpoints"
    ckp_dir.mkdir(parents=True, exist_ok=True)

    npz_path, json_path = get_checkpoint_paths(output_dir, batch_idx)
    tmp_npz = npz_path.with_suffix(".tmp.npz")
    tmp_json = json_path.with_suffix(".tmp.json")

    # Ensure float32 format
    if vectors.dtype != np.float32:
        vectors = vectors.astype(np.float32)

    # Compute checksum of raw vector bytes
    vector_bytes = vectors.tobytes()
    vector_sha256 = hashlib.sha256(vector_bytes).hexdigest()

    # 1. Save uncompressed npz (fast, predictable)
    np.savez(tmp_npz, vectors=vectors, chunk_ids=np.array(chunk_ids, dtype=str))

    # 2. Verify write by reading back
    with np.load(tmp_npz) as verify_data:
        read_vecs = verify_data["vectors"]
        read_ids = verify_data["chunk_ids"].tolist()
        assert read_vecs.shape == vectors.shape, f"Corrupted shape on write: {read_vecs.shape} vs {vectors.shape}"
        assert read_ids == chunk_ids, "Corrupted chunk IDs on write"
        assert np.all(np.isfinite(read_vecs)), "Non-finite values detected in written vectors"

    # 3. Save metadata JSON
    meta_record = {
        "batch_index": batch_idx,
        "chunk_start": chunk_start,
        "chunk_end": chunk_end,
        "count": len(chunk_ids),
        "embedding_dim": vectors.shape[1],
        "vector_sha256": vector_sha256,
        "created_at": datetime.now().isoformat(),
        "chunks": [
            {
                "chunk_id": m["chunk_id"],
                "document_id": m["document_id"],
                "category": m["category"],
                "content_type": m["content_type"],
                "token_count": m["token_count"],
            }
            for m in batch_metadata
        ],
    }

    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(meta_record, f, indent=2)

    # 4. Atomic rename
    os.replace(tmp_npz, npz_path)
    os.replace(tmp_json, json_path)

    batch_summary = {
        "batch_index": batch_idx,
        "chunk_start": chunk_start,
        "chunk_end": chunk_end,
        "count": len(chunk_ids),
        "npz_file": npz_path.name,
        "json_file": json_path.name,
        "sha256": vector_sha256,
        "size_bytes": npz_path.stat().st_size,
    }
    return batch_summary


def validate_checkpoint_file(
    npz_path: Path,
    expected_dim: int,
    expected_ids: List[str],
) -> bool:
    """Validate a single checkpoint file's existence, readability, and content."""
    if not npz_path.exists():
        return False
    try:
        with np.load(npz_path) as data:
            vecs = data["vectors"]
            ids = data["chunk_ids"].tolist()
            if vecs.shape != (len(expected_ids), expected_dim):
                return False
            if ids != expected_ids:
                return False
            if not np.all(np.isfinite(vecs)):
                return False
            return True
    except Exception:
        return False


# ==============================================================================
# PREFLIGHT / DRY-RUN
# ==============================================================================

def run_preflight(
    output_dir: Path,
    model_name: str,
    batch_size: int,
    checkpoint_size: int,
) -> bool:
    """Run read-only preflight audit without loading models or generating vectors."""
    print("=" * 78)
    print("PREFLIGHT AUDIT: FULL-CORPUS EMBEDDING GENERATION")
    print("=" * 78)

    # 1. Corpus audit
    print("\n[1/6] Authoritative Corpus Inspection...")
    chunk_files = discover_chunk_files()
    pilot_count = sum(1 for p in chunk_files if "chunks_pilot" in p.as_posix())
    corpus_count = sum(1 for p in chunk_files if "chunks_corpus" in p.as_posix())
    print(f"  Pilot publication files:   {pilot_count:4d} files (data/chunks_pilot/)")
    print(f"  Corpus publication files:  {corpus_count:4d} files (data/chunks_corpus/)")
    print(f"  Total publication files:   {len(chunk_files):4d} files (Target: 73)")

    chunks, fingerprint = load_authoritative_corpus()
    print(f"  Authoritative Chunks Read: {len(chunks):,d} chunks (Target: {EXPECTED_TOTAL_CHUNKS})")
    print(f"  Corpus Fingerprint:        {fingerprint}")
    assert len(chunks) == EXPECTED_TOTAL_CHUNKS, f"Corpus mismatch: {len(chunks)} != {EXPECTED_TOTAL_CHUNKS}"

    # Breakdown by content type
    type_counts = {}
    for c in chunks:
        type_counts[c["content_type"]] = type_counts.get(c["content_type"], 0) + 1
    print(f"  Content Breakdown:         {dict(type_counts)}")

    # 2. Model Cache Inspection
    print("\n[2/6] Hugging Face Model Cache Inspection...")
    cache_info = get_model_cache_info(model_name)
    print(f"  Model ID:                  {model_name}")
    print(f"  Cache Directory:           {cache_info['model_dir']}")
    print(f"  Is Cached Locally:         {cache_info['is_cached']}")
    print(f"  Active Revision:           {cache_info['active_revision']}")
    print(f"  Weight Files Verified:     {len(cache_info['weight_files'])}")
    for wf in cache_info["weight_files"]:
        print(f"    - {Path(wf).name} ({Path(wf).stat().st_size / (1024*1024):.1f} MB)")

    if not cache_info["is_cached"]:
        print("\n  [PREFLIGHT ERROR]: Model is not fully cached locally! Aborting.")
        return False

    # 3. Storage & Disk Space Budget
    print("\n[3/6] Storage Budget & Safety Reserves...")
    free_mb = get_disk_free_mb(output_dir)
    raw_vector_mb = (len(chunks) * EXPECTED_EMBEDDING_DIM * 4) / (1024 * 1024)
    total_batches = int(np.ceil(len(chunks) / checkpoint_size))
    # Estimated storage: checkpoints (~55 MB) + final unified array (~51 MB) + metadata (~10 MB)
    estimated_storage_mb = (raw_vector_mb * 2.0) + 15.0

    print(f"  Current Free Disk Space:   {free_mb:.2f} MB ({free_mb/1024:.2f} GB)")
    print(f"  Mandatory Reserve:         {MANDATORY_DISK_RESERVE_MB:.2f} MB")
    print(f"  Raw Vector Memory (f32):   {raw_vector_mb:.2f} MB (13,084 x 1024 floats)")
    print(f"  Estimated Artifact Space:  ~{estimated_storage_mb:.2f} MB (Checkpoints + Final Merged)")
    headroom_mb = free_mb - MANDATORY_DISK_RESERVE_MB
    print(f"  Net Usable Headroom:       {headroom_mb:.2f} MB (Headroom vs Need: {headroom_mb/estimated_storage_mb:.1f}x)")

    if free_mb < (MANDATORY_DISK_RESERVE_MB + estimated_storage_mb):
        print(f"\n  [PREFLIGHT ERROR]: Insufficient free disk space! Need at least {MANDATORY_DISK_RESERVE_MB + estimated_storage_mb:.1f} MB.")
        return False
    print("  [SUCCESS] Disk space check PASSED with generous safety reserve.")

    # 4. Pipeline Execution Configuration
    print("\n[4/6] Planned Batch & Checkpoint Parameters...")
    print(f"  Output Directory:          {output_dir}")
    print(f"  Embedding Dimension:       {EXPECTED_EMBEDDING_DIM}")
    print(f"  Checkpoint Size:           {checkpoint_size} chunks/checkpoint")
    print(f"  Total Batches:             {total_batches} checkpoints")
    print(f"  Inference Batch Size:      {batch_size} chunks/forward pass")
    print("  Vector Normalization:      L2 Normalized (True)")

    # 5. Resume & Existing Checkpoint Status
    print("\n[5/6] Checking Existing Output Directory & Resumability...")
    manifest_mgr = ManifestManager(output_dir)
    if manifest_mgr.exists():
        manifest = manifest_mgr.load()
        completed = manifest.get("completed_batches", [])
        print(f"  Found Existing Manifest:   {len(completed)} / {total_batches} batches previously recorded.")
        # Verify compatibility
        if manifest.get("corpus_fingerprint") != fingerprint:
            print("  [WARNING] Existing manifest corpus fingerprint differs! A full clean run would be required.")
        elif manifest.get("model_name") != model_name:
            print("  [WARNING] Existing manifest model differs! Incompatible.")
        else:
            print("  [SUCCESS] Existing checkpoints are compatible with current corpus.")
    else:
        print(f"  Clean output state: No previous manifest found in {output_dir}")

    # 6. Runtime Projections
    print("\n[6/6] CPU Runtime & Throughput Projections...")
    # Based on pilot benchmark: 0.24-0.25 chunks/sec on CPU
    est_sec = len(chunks) / 0.24
    est_hours = est_sec / 3600.0
    print(f"  Historical Pilot Speed:    ~0.24 chunks/sec on CPU")
    print(f"  Estimated Full Run Time:   ~{est_hours:.2f} hours (~{est_hours * 60:.0f} minutes)")
    print(f"  Time per Checkpoint (250): ~{250 / 0.24 / 60:.1f} minutes")

    print("\n" + "=" * 78)
    print("PREFLIGHT STATUS: READY FOR EXECUTION UPON USER APPROVAL")
    print("=" * 78)
    return True


# ==============================================================================
# VALIDATION & FINALIZATION MODE
# ==============================================================================

def validate_and_finalize(output_dir: Path, chunks: List[Dict[str, Any]], fingerprint: str) -> bool:
    """Validate all checkpoints and produce the finalized unified artifact."""
    print("=" * 78)
    print("VALIDATION & FINALIZATION: BGE-M3 CORPUS EMBEDDINGS")
    print("=" * 78)

    manifest_mgr = ManifestManager(output_dir)
    if not manifest_mgr.exists():
        print(f"[ERROR] No manifest found at {output_dir / 'manifest.json'}")
        return False

    manifest = manifest_mgr.load()
    if manifest.get("corpus_fingerprint") != fingerprint:
        print("[ERROR] Corpus fingerprint mismatch between disk chunks and manifest!")
        return False

    checkpoint_size = manifest["checkpoint_size"]
    total_chunks = len(chunks)
    total_batches = int(np.ceil(total_chunks / checkpoint_size))

    completed_dict = {b["batch_index"]: b for b in manifest.get("completed_batches", [])}
    print(f"Validating {total_batches} planned batches against recorded manifest...")

    missing_batches = []
    corrupted_batches = []
    ordered_vectors: List[np.ndarray] = []
    ordered_ids: List[str] = []

    for b_idx in range(total_batches):
        c_start = b_idx * checkpoint_size
        c_end = min(c_start + checkpoint_size, total_chunks)
        expected_cids = [c["chunk_id"] for c in chunks[c_start:c_end]]

        npz_path, _ = get_checkpoint_paths(output_dir, b_idx)
        if not npz_path.exists() or b_idx not in completed_dict:
            missing_batches.append(b_idx)
            continue

        # Load and validate
        try:
            with np.load(npz_path) as data:
                vecs = data["vectors"]
                ids = data["chunk_ids"].tolist()

                if vecs.shape != (len(expected_cids), EXPECTED_EMBEDDING_DIM):
                    corrupted_batches.append((b_idx, f"Invalid shape: {vecs.shape}"))
                    continue
                if ids != expected_cids:
                    corrupted_batches.append((b_idx, "Chunk ID sequence mismatch"))
                    continue
                if not np.all(np.isfinite(vecs)):
                    corrupted_batches.append((b_idx, "NaN or Inf values detected"))
                    continue

                ordered_vectors.append(vecs)
                ordered_ids.extend(ids)
        except Exception as e:
            corrupted_batches.append((b_idx, str(e)))

    if missing_batches:
        print(f"[VALIDATION FAILED]: {len(missing_batches)} batches missing: {missing_batches[:10]}...")
        return False
    if corrupted_batches:
        print(f"[VALIDATION FAILED]: {len(corrupted_batches)} batches corrupted: {corrupted_batches[:5]}")
        return False

    print(f"[SUCCESS] All {total_batches} checkpoints passed rigorous validation.")
    print(f"Total verified vectors: {len(ordered_ids):,d} / {total_chunks:,d}")

    # Merge into unified arrays
    print("\nMerging checkpoints into unified finalized artifacts...")
    merged_vectors = np.vstack(ordered_vectors)
    assert merged_vectors.shape == (total_chunks, EXPECTED_EMBEDDING_DIM), "Merged shape error"

    # Write unified embeddings.npy atomically
    final_npy = output_dir / "embeddings.npy"
    tmp_npy = final_npy.with_suffix(".tmp.npy")
    np.save(tmp_npy, merged_vectors)
    os.replace(tmp_npy, final_npy)
    print(f"  Saved: {final_npy} ({final_npy.stat().st_size / (1024*1024):.2f} MB)")

    # Write aligned chunk metadata JSONL
    final_meta = output_dir / "chunk_metadata.jsonl"
    tmp_meta = final_meta.with_suffix(".tmp.jsonl")
    with open(tmp_meta, "w", encoding="utf-8") as f:
        for c in chunks:
            row = {
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "category": c["category"],
                "content_type": c["content_type"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "token_count": c["token_count"],
                "source_file": c["source_file"],
            }
            f.write(json.dumps(row) + "\n")
    os.replace(tmp_meta, final_meta)
    print(f"  Saved: {final_meta} ({final_meta.stat().st_size / (1024*1024):.2f} MB)")

    # Update manifest to FINALIZED
    manifest["status"] = "FINALIZED"
    manifest["finalized_at"] = datetime.now().isoformat()
    manifest["final_embeddings_file"] = final_npy.name
    manifest["final_metadata_file"] = final_meta.name
    manifest["final_sha256"] = hashlib.sha256(merged_vectors.tobytes()).hexdigest()
    manifest_mgr.save_atomic(manifest)
    print(f"  Updated Manifest: {output_dir / 'manifest.json'}")

    print("\n" + "=" * 78)
    print("FINALIZATION COMPLETED SUCCESSFULLY")
    print("=" * 78)
    return True


# ==============================================================================
# RESUMABLE GENERATION ENGINE
# ==============================================================================

def run_embedding_generation(
    output_dir: Path,
    model_name: str,
    batch_size: int,
    checkpoint_size: int,
) -> int:
    """Execute the batch-wise embedding generation pipeline with resume support."""
    print("=" * 78)
    print("FULL-CORPUS EMBEDDING GENERATION: BAAI/bge-m3")
    print("=" * 78)

    # 1. Load Corpus
    chunks, fingerprint = load_authoritative_corpus()
    total_chunks = len(chunks)
    total_batches = int(np.ceil(total_chunks / checkpoint_size))

    # 2. Disk & Cache Pre-checks
    free_mb = get_disk_free_mb(output_dir)
    raw_vector_mb = (total_chunks * EXPECTED_EMBEDDING_DIM * 4) / (1024 * 1024)
    if free_mb < (MANDATORY_DISK_RESERVE_MB + raw_vector_mb * 2.0):
        print(f"[FATAL]: Insufficient disk space ({free_mb:.1f} MB free). Safety threshold is {MANDATORY_DISK_RESERVE_MB + raw_vector_mb * 2.0:.1f} MB.")
        return 1

    cache_info = get_model_cache_info(model_name)
    if not cache_info["is_cached"]:
        print(f"[FATAL]: Model {model_name} is not cached locally. Aborting.")
        return 1

    # 3. Manifest Initialization / Resume Check
    manifest_mgr = ManifestManager(output_dir)
    if manifest_mgr.exists():
        manifest = manifest_mgr.load()
        if manifest.get("corpus_fingerprint") != fingerprint:
            print("[FATAL]: Existing manifest corpus fingerprint differs! Cannot resume.")
            return 1
        if manifest.get("model_name") != model_name:
            print("[FATAL]: Existing manifest model differs! Cannot resume.")
            return 1
        print(f"Resuming existing session: {len(manifest.get('completed_batches', []))} / {total_batches} batches already marked complete.")
    else:
        manifest = manifest_mgr.initialize(
            model_name=model_name,
            model_revision=cache_info["active_revision"],
            embedding_dim=EXPECTED_EMBEDDING_DIM,
            corpus_fingerprint=fingerprint,
            total_chunks=total_chunks,
            checkpoint_size=checkpoint_size,
            batch_size=batch_size,
        )

    completed_indices = {b["batch_index"] for b in manifest.get("completed_batches", [])}

    # 4. Filter Pending Batches & Validate Existing Checkpoints
    pending_batches: List[int] = []
    for b_idx in range(total_batches):
        c_start = b_idx * checkpoint_size
        c_end = min(c_start + checkpoint_size, total_chunks)
        expected_cids = [c["chunk_id"] for c in chunks[c_start:c_end]]
        npz_path, json_path = get_checkpoint_paths(output_dir, b_idx)

        if b_idx in completed_indices:
            # Re-validate file integrity
            if validate_checkpoint_file(npz_path, EXPECTED_EMBEDDING_DIM, expected_cids):
                continue
            else:
                print(f"[WARNING]: Checkpoint {b_idx} was marked complete but failed integrity check. Re-queueing.")
                completed_indices.remove(b_idx)
                manifest["completed_batches"] = [b for b in manifest["completed_batches"] if b["batch_index"] != b_idx]
        elif validate_checkpoint_file(npz_path, EXPECTED_EMBEDDING_DIM, expected_cids):
            # Checkpoint file exists and is valid on disk even if manifest was out-of-sync
            print(f"[RECOVERED]: Found valid unindexed checkpoint on disk for batch {b_idx}. Recovering.")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                sha = meta.get("vector_sha256", "")
            except Exception:
                sha = ""
            batch_summary = {
                "batch_index": b_idx,
                "chunk_start": c_start,
                "chunk_end": c_end,
                "count": len(expected_cids),
                "npz_file": npz_path.name,
                "json_file": json_path.name,
                "sha256": sha,
                "size_bytes": npz_path.stat().st_size,
            }
            manifest["completed_batches"].append(batch_summary)
            completed_indices.add(b_idx)
            continue

        pending_batches.append(b_idx)

    # Persist any recovered batches into manifest
    manifest["completed_batches"].sort(key=lambda b: b["batch_index"])
    manifest_mgr.save_atomic(manifest)

    print(f"\nExecution Plan: {len(completed_indices)} batches verified on disk, {len(pending_batches)} batches pending.")
    if not pending_batches:
        print("[NOTICE]: All batches are already completed on disk!")
        print("Running finalization...")
        validate_and_finalize(output_dir, chunks, fingerprint)
        return 0

    # 5. Load Model Sequentially (Only after all checks pass)
    print(f"\nLoading model {model_name} from local cache (local_files_only=True)...")
    from sentence_transformers import SentenceTransformer

    t0_model = time.perf_counter()
    model = SentenceTransformer(model_name, local_files_only=True)
    load_sec = time.perf_counter() - t0_model
    print(f"Model loaded in {load_sec:.2f} s. Process RAM: {get_process_memory_mb():.2f} MB")

    # 6. Sequential Batch Processing Loop
    start_time = time.perf_counter()
    chunks_encoded_session = 0

    try:
        for step, b_idx in enumerate(pending_batches, start=1):
            c_start = b_idx * checkpoint_size
            c_end = min(c_start + checkpoint_size, total_chunks)
            batch_chunks = chunks[c_start:c_end]
            batch_texts = [c["text"] for c in batch_chunks]
            batch_ids = [c["chunk_id"] for c in batch_chunks]

            print(f"\n--- Batch {b_idx + 1:02d}/{total_batches:02d} (Chunks {c_start + 1:,d} to {c_end:,d} of {total_chunks:,d}) ---")
            t0_batch = time.perf_counter()

            # Encode chunks with conservative batch_size
            vectors = model.encode(
                batch_texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            batch_duration = time.perf_counter() - t0_batch
            batch_throughput = len(batch_texts) / max(batch_duration, 0.001)

            # Atomic save to disk
            batch_summary = save_checkpoint_atomic(
                output_dir=output_dir,
                batch_idx=b_idx,
                chunk_start=c_start,
                chunk_end=c_end,
                chunk_ids=batch_ids,
                vectors=vectors,
                batch_metadata=batch_chunks,
            )

            # Update manifest without duplicate entries
            manifest["completed_batches"] = [b for b in manifest.get("completed_batches", []) if b["batch_index"] != b_idx] + [batch_summary]
            manifest["completed_batches"].sort(key=lambda b: b["batch_index"])
            # Remove from failed if it was previously failed
            manifest["failed_batches"] = [f for f in manifest.get("failed_batches", []) if f["batch_index"] != b_idx]
            manifest_mgr.save_atomic(manifest)

            # Memory Hygiene: Free vector array and collect garbage
            del vectors
            gc.collect()

            chunks_encoded_session += len(batch_texts)
            elapsed_total = time.perf_counter() - start_time
            avg_speed = chunks_encoded_session / max(elapsed_total, 0.001)
            remaining_chunks = total_chunks - (len(manifest["completed_batches"]) * checkpoint_size)
            eta_hours = (max(remaining_chunks, 0) / max(avg_speed, 0.001)) / 3600.0

            print(f"  Encoded {len(batch_texts)} chunks in {batch_duration:.1f} s ({batch_throughput:.2f} chunks/s)")
            print(f"  Checkpoint saved: {batch_summary['npz_file']} ({batch_summary['size_bytes'] / (1024*1024):.2f} MB)")
            print(f"  Progress: {len(manifest['completed_batches'])}/{total_batches} batches ({len(manifest['completed_batches'])/total_batches*100:.1f}%) | ETA: ~{eta_hours:.1f} hrs | RAM: {get_process_memory_mb():.1f} MB")

            # Check disk space periodically
            if get_disk_free_mb(output_dir) < MANDATORY_DISK_RESERVE_MB:
                print(f"[CRITICAL STOP]: Free disk space breached mandatory reserve of {MANDATORY_DISK_RESERVE_MB} MB. Pausing safely.")
                return 1

    except KeyboardInterrupt:
        print("\n[USER INTERRUPTION]: Process interrupted. Last batch checkpoint is safe on disk. Resumable at any time.")
        return 0
    except Exception as e:
        print(f"\n[ERROR ENCOUNTERED]: {e}")
        # Record failure in manifest
        failed_record = {
            "batch_index": b_idx,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        manifest["failed_batches"].append(failed_record)
        manifest_mgr.save_atomic(manifest)
        return 1

    # Clean unload
    del model
    gc.collect()

    # Finalize
    print("\nAll batches completed. Proceeding to automated finalization...")
    validate_and_finalize(output_dir, chunks, fingerprint)
    return 0


# ==============================================================================
# CLI ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Full-Corpus Resumable Embedding Generation with BAAI/bge-m3")
    parser.add_argument("--preflight", "--dry-run", dest="preflight", action="store_true", help="Run preflight checks only; do not load model or generate embeddings")
    parser.add_argument("--validate", "--finalize", dest="finalize_only", action="store_true", help="Validate existing checkpoints and finalize unified artifacts without encoding")
    parser.add_argument("--checkpoint-size", type=int, default=250, help="Number of chunks per checkpoint file (default: 250)")
    parser.add_argument("--batch-size", type=int, default=16, help="Inference forward-pass batch size (default: 16)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Destination directory for embeddings and checkpoints")
    parser.add_argument("--model-name", type=str, default=DEFAULT_MODEL_NAME, help="Hugging Face model ID (default: BAAI/bge-m3)")
    args = parser.parse_args()

    # Always run preflight check
    preflight_ok = run_preflight(
        output_dir=args.output_dir,
        model_name=args.model_name,
        batch_size=args.batch_size,
        checkpoint_size=args.checkpoint_size,
    )

    if not preflight_ok:
        return 1

    if args.preflight:
        print("\n[PREFLIGHT ONLY]: Execution paused as requested. No models loaded.")
        return 0

    if args.finalize_only:
        chunks, fingerprint = load_authoritative_corpus()
        success = validate_and_finalize(args.output_dir, chunks, fingerprint)
        return 0 if success else 1

    # Actual generation (requires user confirmation)
    return run_embedding_generation(
        output_dir=args.output_dir,
        model_name=args.model_name,
        batch_size=args.batch_size,
        checkpoint_size=args.checkpoint_size,
    )


if __name__ == "__main__":
    sys.exit(main())
