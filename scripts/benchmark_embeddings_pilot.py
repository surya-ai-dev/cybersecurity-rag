#!/usr/bin/env python3
"""Pilot Benchmark Runner: BAAI/bge-small-en-v1.5 vs BAAI/bge-m3.

Evaluates dense retrieval performance and resource consumption on a representative
396-chunk cloud security cohort (NIST SP 800-144 & NIST SP 800-146) against the 15
verified evaluation questions in data/evaluation/retrieval_ground_truth_current.json.

Safety & Constraints:
- Purely in-memory evaluation (NumPy cosine similarity).
- 0 MB disk writes for vector storage; no Qdrant or external vector DB required.
- Strict sequential model execution with garbage collection between models.
- local_files_only=True to prevent network calls or downloads.
"""

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psutil

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Paths
GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_current.json"
PILOT_CHUNK_FILES = [
    PROJECT_ROOT / "data" / "chunks_corpus" / "cloud_application_security" / "NIST_SP_800-144_chunks.jsonl",
    PROJECT_ROOT / "data" / "chunks_corpus" / "cloud_application_security" / "NIST_SP_800-146_chunks.jsonl",
]

MODELS = [
    {
        "name": "BAAI/bge-small-en-v1.5",
        "alias": "BGE-Small (Baseline)",
        "dim": 384,
        "max_seq_len": 512,
    },
    {
        "name": "BAAI/bge-m3",
        "alias": "BGE-M3 (Candidate)",
        "dim": 1024,
        "max_seq_len": 8192,
    },
]


def get_process_memory_mb() -> float:
    """Return current process Resident Set Size (RSS) in megabytes."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def load_chunks(chunk_paths: List[Path]) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    """Load chunks from jsonl files.

    Returns:
        chunk_ids: list of chunk ID strings
        chunk_texts: list of chunk text strings
        chunk_metas: list of chunk metadata dictionaries
    """
    chunk_ids = []
    chunk_texts = []
    chunk_metas = []

    for path in chunk_paths:
        if not path.exists():
            raise FileNotFoundError(f"Chunk file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    chunk_ids.append(item["chunk_id"])
                    chunk_texts.append(item.get("text", ""))
                    chunk_metas.append(item)

    return chunk_ids, chunk_texts, chunk_metas


def load_ground_truth(gt_path: Path, only_eligible: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load ground truth mapping."""
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    with open(gt_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if only_eligible:
        return {k: v for k, v in data.items() if v.get("evaluation_eligible", True) and v.get("relevant_chunks")}
    return data


def calculate_metrics(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    top_k: int = 5,
) -> Dict[str, float]:
    """Calculate Hit@1, Hit@3, Hit@5, Precision@5, and MRR for a single query."""
    rel_set = set(relevant_ids)

    # Hit@K
    hit_1 = 1.0 if any(cid in rel_set for cid in retrieved_ids[:1]) else 0.0
    hit_3 = 1.0 if any(cid in rel_set for cid in retrieved_ids[:3]) else 0.0
    hit_5 = 1.0 if any(cid in rel_set for cid in retrieved_ids[:5]) else 0.0

    # Precision@K
    top_k_retrieved = retrieved_ids[:top_k]
    rel_count = sum(1 for cid in top_k_retrieved if cid in rel_set)
    precision_k = rel_count / max(len(top_k_retrieved), 1)

    # MRR (Mean Reciprocal Rank)
    mrr = 0.0
    for rank, cid in enumerate(top_k_retrieved):
        if cid in rel_set:
            mrr = 1.0 / (rank + 1)
            break

    return {
        "hit@1": hit_1,
        "hit@3": hit_3,
        "hit@5": hit_5,
        "precision@5": precision_k,
        "mrr": mrr,
    }


def evaluate_single_model(
    model_cfg: Dict[str, Any],
    chunk_ids: List[str],
    chunk_texts: List[str],
    ground_truth: Dict[str, Dict[str, Any]],
    top_k: int = 5,
) -> Dict[str, Any]:
    """Load model, encode chunks, score queries, and compute retrieval metrics."""
    from sentence_transformers import SentenceTransformer

    model_name = model_cfg["name"]
    alias = model_cfg["alias"]
    print(f"\n{'='*70}")
    print(f"BENCHMARKING: {alias} ({model_name})")
    print(f"{'='*70}")

    initial_ram = get_process_memory_mb()
    print(f"Initial Process RAM: {initial_ram:.2f} MB")

    # 1. Model Loading
    t0_load = time.perf_counter()
    model = SentenceTransformer(model_name, local_files_only=True)
    load_time_sec = time.perf_counter() - t0_load
    loaded_ram = get_process_memory_mb()
    model_ram_delta = loaded_ram - initial_ram
    print(f"Model Load Time: {load_time_sec:.3f} s")
    print(f"RAM after Model Load: {loaded_ram:.2f} MB (+{model_ram_delta:.2f} MB)")

    # 2. Corpus Encoding
    print(f"Encoding {len(chunk_texts)} chunks into memory (batch_size=16)...")
    t0_enc = time.perf_counter()
    corpus_embeddings = model.encode(
        chunk_texts,
        batch_size=16,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    encoding_time_sec = time.perf_counter() - t0_enc
    throughput = len(chunk_texts) / max(encoding_time_sec, 0.001)
    encoded_ram = get_process_memory_mb()
    vector_memory_delta = encoded_ram - loaded_ram
    print(f"Corpus Encoding Time: {encoding_time_sec:.3f} s ({throughput:.2f} chunks/sec)")
    print(f"Embedding Array Shape: {corpus_embeddings.shape} (dtype={corpus_embeddings.dtype})")
    print(f"RAM after Encoding: {encoded_ram:.2f} MB (+{vector_memory_delta:.2f} MB)")

    # 3. Query Scoring
    print(f"\nEvaluating {len(ground_truth)} ground-truth queries...")
    query_latencies = []
    per_query_metrics = {}

    for qid, qentry in ground_truth.items():
        question = qentry["question"]
        relevant_ids = qentry["relevant_chunks"]

        t0_q = time.perf_counter()
        q_emb = model.encode(
            question,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        q_latency_ms = (time.perf_counter() - t0_q) * 1000.0
        query_latencies.append(q_latency_ms)

        # Cosine similarity via dot product (both are L2-normalized)
        sim_scores = np.dot(corpus_embeddings, q_emb)
        top_indices = np.argsort(-sim_scores)[:top_k]
        retrieved_cids = [chunk_ids[idx] for idx in top_indices]

        metrics = calculate_metrics(retrieved_cids, relevant_ids, top_k=top_k)
        metrics["query_latency_ms"] = q_latency_ms
        metrics["retrieved_chunks"] = retrieved_cids
        metrics["top1_score"] = float(sim_scores[top_indices[0]])
        per_query_metrics[qid] = metrics

    # 4. Aggregations
    mean_hit1 = np.mean([m["hit@1"] for m in per_query_metrics.values()]) * 100.0
    mean_hit3 = np.mean([m["hit@3"] for m in per_query_metrics.values()]) * 100.0
    mean_hit5 = np.mean([m["hit@5"] for m in per_query_metrics.values()]) * 100.0
    mean_prec5 = np.mean([m["precision@5"] for m in per_query_metrics.values()]) * 100.0
    mean_mrr = np.mean([m["mrr"] for m in per_query_metrics.values()])
    mean_latency = np.mean(query_latencies)

    print(f"Results for {alias}:")
    print(f"  Hit@1:        {mean_hit1:6.2f}%")
    print(f"  Hit@3:        {mean_hit3:6.2f}%")
    print(f"  Hit@5:        {mean_hit5:6.2f}%")
    print(f"  Precision@5:  {mean_prec5:6.2f}%")
    print(f"  MRR:          {mean_mrr:6.4f}")
    print(f"  Avg Latency:  {mean_latency:6.2f} ms")

    # 5. Clean Model Unload & GC
    print("\nUnloading model and releasing memory...")
    del model
    del corpus_embeddings
    gc.collect()
    time.sleep(0.5)
    final_ram = get_process_memory_mb()
    print(f"RAM after Unload & GC: {final_ram:.2f} MB (Delta from peak: -{encoded_ram - final_ram:.2f} MB)")

    return {
        "model_name": model_name,
        "alias": alias,
        "dim": model_cfg["dim"],
        "load_time_sec": load_time_sec,
        "model_ram_delta_mb": model_ram_delta,
        "encoding_time_sec": encoding_time_sec,
        "throughput_chunks_per_sec": throughput,
        "avg_query_latency_ms": mean_latency,
        "hit@1": mean_hit1,
        "hit@3": mean_hit3,
        "hit@5": mean_hit5,
        "precision@5": mean_prec5,
        "mrr": mean_mrr,
        "per_query_results": per_query_metrics,
    }


def main():
    parser = argparse.ArgumentParser(description="Pilot Benchmark: BGE-small vs BGE-M3")
    parser.add_argument("--dry-run", action="store_true", help="Validate corpus and ground truth without loading models")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K retrieval limit (default 5)")
    args = parser.parse_args()

    print("=" * 70)
    print("EMBEDDING MODEL PILOT BENCHMARK PREFLIGHT & RUNNER")
    print("=" * 70)

    # 1. Load Chunks
    print(f"Loading chunks from {len(PILOT_CHUNK_FILES)} files...")
    chunk_ids, chunk_texts, chunk_metas = load_chunks(PILOT_CHUNK_FILES)
    print(f"Loaded {len(chunk_ids)} chunks (SP 800-144: 164, SP 800-146: 232).")

    # 2. Load Ground Truth
    ground_truth = load_ground_truth(GROUND_TRUTH_FILE, only_eligible=True)
    print(f"Loaded {len(ground_truth)} verified, evaluation-eligible questions.")

    if args.dry_run:
        print("\n[DRY RUN COMPLETED]: Corpus chunks and ground truth successfully verified.")
        print(f"Target Models: {[m['name'] for m in MODELS]}")
        print("Ready for execution upon approval.")
        return 0

    # 3. Sequential Benchmark
    results = []
    for model_cfg in MODELS:
        res = evaluate_single_model(
            model_cfg=model_cfg,
            chunk_ids=chunk_ids,
            chunk_texts=chunk_texts,
            ground_truth=ground_truth,
            top_k=args.top_k,
        )
        results.append(res)

    # 4. Comparative Matrix
    print("\n" + "=" * 70)
    print("FINAL HEAD-TO-HEAD COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Metric':<28} {'BGE-Small (Baseline)':<22} {'BGE-M3 (Candidate)':<22}")
    print("-" * 70)
    r1, r2 = results[0], results[1]
    print(f"{'Embedding Dimension':<28} {r1['dim']:<22} {r2['dim']:<22}")
    print(f"{'Model Load Time':<28} {r1['load_time_sec']:.2f} s{'':<16} {r2['load_time_sec']:.2f} s")
    print(f"{'Model RAM Delta':<28} +{r1['model_ram_delta_mb']:.1f} MB{'':<14} +{r2['model_ram_delta_mb']:.1f} MB")
    print(f"{'Corpus Encoding Time':<28} {r1['encoding_time_sec']:.2f} s{'':<16} {r2['encoding_time_sec']:.2f} s")
    print(f"{'Throughput (chunks/sec)':<28} {r1['throughput_chunks_per_sec']:.1f}{'':<18} {r2['throughput_chunks_per_sec']:.1f}")
    print(f"{'Avg Query Latency':<28} {r1['avg_query_latency_ms']:.1f} ms{'':<15} {r2['avg_query_latency_ms']:.1f} ms")
    print("-" * 70)
    print(f"{'Hit@1':<28} {r1['hit@1']:.2f}%{'':<15} {r2['hit@1']:.2f}%")
    print(f"{'Hit@3':<28} {r1['hit@3']:.2f}%{'':<15} {r2['hit@3']:.2f}%")
    print(f"{'Hit@5':<28} {r1['hit@5']:.2f}%{'':<15} {r2['hit@5']:.2f}%")
    print(f"{'Precision@5':<28} {r1['precision@5']:.2f}%{'':<15} {r2['precision@5']:.2f}%")
    print(f"{'MRR':<28} {r1['mrr']:.4f}{'':<16} {r2['mrr']:.4f}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
