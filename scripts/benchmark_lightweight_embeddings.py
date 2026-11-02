#!/usr/bin/env python3
"""Lightweight Embedding Benchmark Runner.

Compares lightweight embedding models on CPU against the NIST Cybersecurity RAG pilot cohort:
1. BAAI/bge-small-en-v1.5 (384 dimensions) - Baseline
2. intfloat/e5-small-v2 (384 dimensions) - Candidate
3. sentence-transformers/all-MiniLM-L6-v2 (384 dimensions) - Candidate

Includes recorded historical BGE-M3 results as a non-evaluated reference.

Evaluation Cohort:
- 396 structure-aware chunks (NIST SP 800-144 & NIST SP 800-146)
- 15 verified, evaluation-eligible queries from data/evaluation/retrieval_ground_truth_current.json

Safety & Constraints:
- Purely in-memory evaluation (NumPy cosine similarity, 0 MB disk writes).
- No vector database required (Qdrant bypassed).
- Strict sequential model execution with garbage collection between models.
- local_files_only=True: Never downloads models or packages automatically.
- Model cache validation: Skips unavailable models gracefully without crashing.
- Preserves all existing chunks, ground-truth files, and historical reports.
"""

import argparse
import gc
import json
import os
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

# File paths
GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_current.json"
PILOT_CHUNK_FILES = [
    PROJECT_ROOT / "data" / "chunks_corpus" / "cloud_application_security" / "NIST_SP_800-144_chunks.jsonl",
    PROJECT_ROOT / "data" / "chunks_corpus" / "cloud_application_security" / "NIST_SP_800-146_chunks.jsonl",
]
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "reports" / "benchmark_lightweight_results.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "reports" / "embedding_benchmark_lightweight_report.md"

# Model specifications
LIGHTWEIGHT_MODELS = [
    {
        "name": "BAAI/bge-small-en-v1.5",
        "alias": "BGE-Small-en-v1.5",
        "role": "Baseline",
        "dim": 384,
        "query_prefix": "",
        "passage_prefix": "",
        "description": "BERT-based 12-layer model (33.4M params), direct symmetric encoding.",
    },
    {
        "name": "intfloat/e5-small-v2",
        "alias": "E5-Small-v2",
        "role": "Candidate",
        "dim": 384,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "description": "BERT-based 12-layer model (33.4M params), asymmetric query/passage prefixes.",
    },
    {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "alias": "MiniLM-L6-v2",
        "role": "Candidate",
        "dim": 384,
        "query_prefix": "",
        "passage_prefix": "",
        "description": "MiniLM 6-layer model (22.7M params), standard sentence-transformers encoding.",
    },
]

# Historical BGE-M3 baseline reference (Strictly for comparison, NOT re-evaluated)
HISTORICAL_BGE_M3_REFERENCE = {
    "model_name": "BAAI/bge-m3",
    "alias": "BGE-M3 [Historical Reference]",
    "role": "Historical Reference (Heavyweight)",
    "dim": 1024,
    "is_historical": True,
    "hit@1": 46.67,
    "hit@3": 73.33,
    "hit@5": 73.33,
    "precision@5": 21.33,
    "mrr": 0.6000,
    "encoding_time_sec": 1600.021,
    "throughput_chunks_per_sec": 0.25,
    "avg_query_latency_ms": 564.58,
    "load_time_sec": 7.00,
    "model_ram_delta_mb": 338.04,
    "notes": "Historical reference recorded during Stage 2 pilot benchmark (1,679.3s encoding time, 0.24-0.25 chunks/s on CPU).",
}


def get_process_memory_mb() -> float:
    """Return current process Resident Set Size (RSS) in megabytes."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def is_model_cached(model_name: str) -> bool:
    """Check if model repository exists with snapshots in the local Hugging Face cache."""
    cache_dir = Path(os.getenv("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
    folder_name = "models--" + model_name.replace("/", "--")
    model_dir = cache_dir / folder_name
    if not model_dir.exists():
        return False
    snapshots_dir = model_dir / "snapshots"
    if not snapshots_dir.exists():
        return False
    for snap in snapshots_dir.iterdir():
        if snap.is_dir() and any(snap.iterdir()):
            return True
    return False


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


def validate_ground_truth_in_corpus(
    ground_truth: Dict[str, Dict[str, Any]],
    chunk_ids: List[str],
) -> Tuple[bool, List[Tuple[str, str]]]:
    """Validate that every referenced ground-truth chunk ID exists in the chunk pool."""
    chunk_set = set(chunk_ids)
    missing = []
    for qid, entry in ground_truth.items():
        for cid in entry.get("relevant_chunks", []):
            if cid not in chunk_set:
                missing.append((qid, cid))
    return len(missing) == 0, missing


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
    batch_size: int = 16,
) -> Dict[str, Any]:
    """Load model, encode chunks, score queries, and compute retrieval metrics."""
    from sentence_transformers import SentenceTransformer

    model_name = model_cfg["name"]
    alias = model_cfg["alias"]
    query_prefix = model_cfg.get("query_prefix", "")
    passage_prefix = model_cfg.get("passage_prefix", "")

    print(f"\n{'='*75}")
    print(f"BENCHMARKING: {alias} ({model_name})")
    print(f"Role: {model_cfg['role']} | Dimension: {model_cfg['dim']}")
    if query_prefix or passage_prefix:
        print(f"Prefixes: Query='{query_prefix}', Passage='{passage_prefix}'")
    else:
        print("Prefixes: None (Standard symmetric encoding)")
    print(f"{'='*75}")

    initial_ram = get_process_memory_mb()
    print(f"Initial Process RAM: {initial_ram:.2f} MB")

    # 1. Model Loading
    t0_load = time.perf_counter()
    model = SentenceTransformer(model_name, local_files_only=True)
    load_time_sec = time.perf_counter() - t0_load
    loaded_ram = get_process_memory_mb()
    model_ram_delta = loaded_ram - initial_ram
    print(f"Model Load Time: {load_time_sec:.3f} s")
    print(f"RAM after Model Load: {loaded_ram:.2f} MB (Delta: +{model_ram_delta:.2f} MB)")

    # 2. Corpus Encoding (with passage_prefix if applicable)
    formatted_texts = [f"{passage_prefix}{text}" for text in chunk_texts] if passage_prefix else chunk_texts
    print(f"Encoding {len(formatted_texts)} chunks into memory (batch_size={batch_size})...")
    t0_enc = time.perf_counter()
    corpus_embeddings = model.encode(
        formatted_texts,
        batch_size=batch_size,
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
    print(f"RAM after Encoding: {encoded_ram:.2f} MB (Vector memory delta: +{vector_memory_delta:.2f} MB)")

    # 3. Query Scoring (with query_prefix if applicable)
    print(f"\nEvaluating {len(ground_truth)} ground-truth queries...")
    query_latencies = []
    per_query_metrics = {}

    for qid, qentry in ground_truth.items():
        question = qentry["question"]
        relevant_ids = qentry["relevant_chunks"]

        formatted_query = f"{query_prefix}{question}" if query_prefix else question

        t0_q = time.perf_counter()
        q_emb = model.encode(
            formatted_query,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        q_latency_ms = (time.perf_counter() - t0_q) * 1000.0
        query_latencies.append(q_latency_ms)

        # Cosine similarity via dot product (both normalized)
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
    print(f"RAM after Unload & GC: {final_ram:.2f} MB (Peak delta recovered: -{encoded_ram - final_ram:.2f} MB)")

    return {
        "model_name": model_name,
        "alias": alias,
        "role": model_cfg["role"],
        "status": "COMPLETED",
        "is_historical": False,
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


def generate_markdown_report(
    evaluated_results: List[Dict[str, Any]],
    historical_ref: Dict[str, Any],
    skipped_models: List[Dict[str, Any]],
    chunk_count: int,
    query_count: int,
) -> str:
    """Generate a clean GitHub-flavored markdown report."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = []
    md.append("# Lightweight Embedding Benchmark Report")
    md.append("")
    md.append(f"**Date**: {now_str}  ")
    md.append(f"**Evaluation Corpus**: {chunk_count} structure-aware chunks (NIST SP 800-144 & SP 800-146)  ")
    md.append(f"**Evaluation Queries**: {query_count} verified questions from `retrieval_ground_truth_current.json`  ")
    md.append(f"**Hardware Environment**: CPU-only PyTorch execution on 16 GB RAM  ")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Executive Summary")
    md.append("")
    md.append("This benchmark evaluates lightweight embedding models (384-dimensional) on CPU for the Cybersecurity RAG project. ")
    md.append("It compares their retrieval accuracy (Hit@K, Precision@5, MRR) and runtime efficiency (load time, throughput, query latency) ")
    md.append("against the recorded historical baseline for `BAAI/bge-m3`.")
    md.append("")

    # Model Status Summary
    md.append("### Evaluated & Reference Models")
    md.append("")
    md.append("| Model Alias | Repository ID | Dimension | Evaluation Status | Role |")
    md.append("| :--- | :--- | :---: | :---: | :--- |")
    for res in evaluated_results:
        md.append(f"| **{res['alias']}** | `{res['model_name']}` | {res['dim']} | **EVALUATED** | {res['role']} |")
    for skipped in skipped_models:
        md.append(f"| **{skipped['alias']}** | `{skipped['name']}` | {skipped['dim']} | **SKIPPED (Not cached locally)** | {skipped['role']} |")
    md.append(f"| **{historical_ref['alias']}** | `{historical_ref['model_name']}` | {historical_ref['dim']} | **HISTORICAL REFERENCE** | {historical_ref['role']} |")
    md.append("")
    md.append("---")
    md.append("")

    # Main Comparative Table
    md.append("## 2. Comparative Metric Table")
    md.append("")
    md.append("> [!NOTE]")
    md.append("> BGE-M3 results are strictly **historical reference numbers** recorded during the Stage 2 pilot benchmark and were not re-evaluated during this run.")
    md.append("")

    # Build header
    cols = ["Metric Category", "Metric"]
    for res in evaluated_results:
        cols.append(f"{res['alias']}")
    cols.append(f"{historical_ref['alias']}")

    md.append("| " + " | ".join(cols) + " |")
    md.append("| " + " | ".join([":---" if i < 2 else ":---:" for i in range(len(cols))]) + " |")

    # Metrics rows
    def fmt_pct(val): return f"{val:.2f}%" if val is not None else "N/A"
    def fmt_num(val, dec=4): return f"{val:.{dec}f}" if val is not None else "N/A"

    rows = [
        ("Architecture", "Parameters", [("33.4M" if "bge-small" in r['model_name'] else ("22.7M" if "MiniLM" in r['model_name'] else "33.4M")) for r in evaluated_results] + ["560M"]),
        ("Architecture", "Vector Dimension", [str(r['dim']) for r in evaluated_results] + [str(historical_ref['dim'])]),
        ("Retrieval Accuracy", "Hit@1", [fmt_pct(r.get('hit@1')) for r in evaluated_results] + [fmt_pct(historical_ref.get('hit@1'))]),
        ("Retrieval Accuracy", "Hit@3", [fmt_pct(r.get('hit@3')) for r in evaluated_results] + [fmt_pct(historical_ref.get('hit@3'))]),
        ("Retrieval Accuracy", "Hit@5", [fmt_pct(r.get('hit@5')) for r in evaluated_results] + [fmt_pct(historical_ref.get('hit@5'))]),
        ("Retrieval Accuracy", "Precision@5", [fmt_pct(r.get('precision@5')) for r in evaluated_results] + [fmt_pct(historical_ref.get('precision@5'))]),
        ("Retrieval Accuracy", "MRR", [fmt_num(r.get('mrr')) for r in evaluated_results] + [fmt_num(historical_ref.get('mrr'))]),
        ("Computational Speed", "Model Load Time", [f"{r['load_time_sec']:.2f} s" for r in evaluated_results] + [f"{historical_ref['load_time_sec']:.2f} s"]),
        ("Computational Speed", "Corpus Encoding (396 chunks)", [f"{r['encoding_time_sec']:.2f} s" for r in evaluated_results] + [f"{historical_ref['encoding_time_sec']:.2f} s"]),
        ("Computational Speed", "CPU Throughput", [f"{r['throughput_chunks_per_sec']:.2f} chunks/s" for r in evaluated_results] + [f"{historical_ref['throughput_chunks_per_sec']:.2f} chunks/s"]),
        ("Computational Speed", "Avg Query Latency", [f"{r['avg_query_latency_ms']:.1f} ms" for r in evaluated_results] + [f"{historical_ref['avg_query_latency_ms']:.1f} ms"]),
        ("Memory Footprint", "Model RAM Delta", [f"+{r['model_ram_delta_mb']:.1f} MB" for r in evaluated_results] + [f"+{historical_ref['model_ram_delta_mb']:.1f} MB"]),
    ]

    for cat, metric_name, vals in rows:
        md.append(f"| **{cat}** | {metric_name} | " + " | ".join(vals) + " |")

    md.append("")
    md.append("---")
    md.append("")

    # Measurement Methodology & Limitations
    md.append("## 3. Methodology & Measurement Limitations")
    md.append("")
    md.append("1. **Ranking Methodology**: All embeddings are $L_2$-normalized; cosine similarity is computed directly via in-memory dot product `corpus_embeddings @ query_embedding`.")
    md.append("2. **Prefix Rules**: E5 models require `query: ` for questions and `passage: ` for documents; BGE-small and MiniLM use direct text encoding without prefixes.")
    md.append("3. **RAM Tracking**: Process Resident Set Size (RSS) is sampled using `psutil`. Notice that Python runtime garbage collection and OS paging can introduce slight non-linear fluctuations in RSS delta.")
    md.append(r"4. **CPU Latency**: Timings are measured on CPU with single-process PyTorch execution. Background OS tasks may introduce modest run-to-run jitter ($\pm 5\%$).")
    md.append("")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Lightweight Embedding Benchmark Runner")
    parser.add_argument("--dry-run", action="store_true", help="Preflight validation only; do not load models or embed chunks")
    parser.add_argument("--models", nargs="+", help="Specific model IDs to run (default: all 3 lightweight models)")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K retrieval limit (default 5)")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size for corpus encoding (default 16)")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON, help="Path to save machine-readable results JSON")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD, help="Path to save Markdown comparison report")
    args = parser.parse_args()

    print("=" * 75)
    print("LIGHTWEIGHT EMBEDDING BENCHMARK PREFLIGHT & RUNNER")
    print("=" * 75)

    # 1. Load Chunks
    print(f"\n[Step 1] Loading pilot chunks from {len(PILOT_CHUNK_FILES)} files...")
    chunk_ids, chunk_texts, chunk_metas = load_chunks(PILOT_CHUNK_FILES)
    print(f"  Loaded {len(chunk_ids)} chunks (SP 800-144: 164, SP 800-146: 232).")

    # 2. Load Ground Truth
    print("\n[Step 2] Loading current ground truth...")
    ground_truth = load_ground_truth(GROUND_TRUTH_FILE, only_eligible=True)
    print(f"  Loaded {len(ground_truth)} verified, evaluation-eligible questions.")

    # 3. Validate Ground Truth in Chunk Pool
    print("\n[Step 3] Validating ground truth chunk IDs against pilot chunk pool...")
    is_valid, missing_ids = validate_ground_truth_in_corpus(ground_truth, chunk_ids)
    if not is_valid:
        print(f"  [ERROR] {len(missing_ids)} ground-truth chunks missing from active chunk pool:")
        for qid, cid in missing_ids:
            print(f"    - Query {qid}: missing {cid}")
        return 1
    print("  [SUCCESS] All referenced ground-truth chunk IDs exist in the active pilot pool.")

    # 4. Check Model Cache Availability
    print("\n[Step 4] Checking local cache availability for lightweight models...")
    selected_names = set(args.models) if args.models else {m["name"] for m in LIGHTWEIGHT_MODELS}
    models_to_run = []
    skipped_models = []

    for m in LIGHTWEIGHT_MODELS:
        if m["name"] not in selected_names:
            continue
        cached = is_model_cached(m["name"])
        if cached:
            print(f"  [AVAILABLE] {m['alias']} (`{m['name']}`)")
            models_to_run.append(m)
        else:
            print(f"  [UNAVAILABLE - SKIPPED] {m['alias']} (`{m['name']}`) is NOT cached locally.")
            skipped_models.append(m)

    # Preflight / Dry-run handling
    if args.dry_run:
        print("\n" + "=" * 75)
        print("[DRY RUN COMPLETED SUCCESSFULLY]")
        print("=" * 75)
        print(f"  Active Chunks:       {len(chunk_ids)}")
        print(f"  Verified Queries:    {len(ground_truth)}")
        print(f"  Models Available:    {[m['alias'] for m in models_to_run]}")
        print(f"  Models Skipped:      {[m['alias'] for m in skipped_models]}")
        print(f"  Historical Baseline: {HISTORICAL_BGE_M3_REFERENCE['alias']}")
        print("\nPreflight verification complete. Ready for manual execution upon user approval.")
        return 0

    if not models_to_run:
        print("\n[ERROR] No candidate models are available in local cache. Aborting run.")
        return 1

    # 5. Sequential Execution
    print(f"\n[Step 5] Executing sequential benchmarks for {len(models_to_run)} available models...")
    evaluated_results = []

    for model_cfg in models_to_run:
        res = evaluate_single_model(
            model_cfg=model_cfg,
            chunk_ids=chunk_ids,
            chunk_texts=chunk_texts,
            ground_truth=ground_truth,
            top_k=args.top_k,
            batch_size=args.batch_size,
        )
        evaluated_results.append(res)

    # 6. Display Summary Table
    print("\n" + "=" * 75)
    print("FINAL HEAD-TO-HEAD COMPARISON SUMMARY")
    print("=" * 75)

    header_names = [r["alias"] for r in evaluated_results] + [HISTORICAL_BGE_M3_REFERENCE["alias"]]
    header_line = f"{'Metric':<26} " + " ".join([f"{name:<22}" for name in header_names])
    print(header_line)
    print("-" * len(header_line))

    def get_val(r, k, fmt="{:.2f}%"):
        v = r.get(k)
        return fmt.format(v) if v is not None else "N/A"

    print(f"{'Embedding Dimension':<26} " + " ".join([f"{str(r.get('dim', '')): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Model Load Time':<26} " + " ".join([f"{get_val(r, 'load_time_sec', '{:.2f} s'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Corpus Encoding (396)':<26} " + " ".join([f"{get_val(r, 'encoding_time_sec', '{:.2f} s'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Throughput (chunks/s)':<26} " + " ".join([f"{get_val(r, 'throughput_chunks_per_sec', '{:.2f}'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Avg Query Latency':<26} " + " ".join([f"{get_val(r, 'avg_query_latency_ms', '{:.1f} ms'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print("-" * len(header_line))
    print(f"{'Hit@1':<26} " + " ".join([f"{get_val(r, 'hit@1'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Hit@3':<26} " + " ".join([f"{get_val(r, 'hit@3'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Hit@5':<26} " + " ".join([f"{get_val(r, 'hit@5'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'Precision@5':<26} " + " ".join([f"{get_val(r, 'precision@5'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print(f"{'MRR':<26} " + " ".join([f"{get_val(r, 'mrr', '{:.4f}'): <22}" for r in evaluated_results + [HISTORICAL_BGE_M3_REFERENCE]]))
    print("=" * len(header_line))

    # 7. Save Artifacts
    output_data = {
        "benchmark_timestamp": datetime.now().isoformat(),
        "chunk_count": len(chunk_ids),
        "query_count": len(ground_truth),
        "evaluated_models": evaluated_results,
        "skipped_models": skipped_models,
        "historical_reference": HISTORICAL_BGE_M3_REFERENCE,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n[Saved Machine-Readable Results]: {args.output_json}")

    md_report = generate_markdown_report(
        evaluated_results=evaluated_results,
        historical_ref=HISTORICAL_BGE_M3_REFERENCE,
        skipped_models=skipped_models,
        chunk_count=len(chunk_ids),
        query_count=len(ground_truth),
    )
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"[Saved Markdown Report]: {args.output_md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
