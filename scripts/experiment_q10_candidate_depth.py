"""Controlled Candidate-Depth Retrieval Experiment on Question Q10.

Tests four configurations on Q10:
  A. Baseline: Dense top 20, BM25 top 20, RRF pool 20, reranker enabled, final top 5.
  B. Expanded retrieval: Dense top 30, BM25 top 30, RRF pool 30, reranker enabled, final top 5.
  C. Larger candidate pool: Dense top 50, BM25 top 50, RRF pool 50, reranker enabled, final top 5.
  D. Larger candidate pool without reranking: Dense top 50, BM25 top 50, RRF pool 50, reranker disabled, final top 5.

Records for every configuration:
  1. Whether each of the three ground-truth chunks was retrieved in the candidate pool & final top 5.
  2. Each target chunk's dense rank and score.
  3. Each target chunk's BM25 rank and score.
  4. Each target chunk's RRF rank and score.
  5. Each target chunk's reranker rank and score (if enabled).
  6. Hit@5, Recall@5, MRR@5, NDCG@5.
  7. Retrieval latency and reranking latency separately.
  8. The actual final five chunk IDs.

Output Artifacts:
  reports/retrieval_evaluation/experiment_q10_candidate_depth.json
  reports/retrieval_evaluation/experiment_q10_candidate_depth.md
"""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import RRFFusion

# Constants for Q10
QUESTION_ID = "Q10"
QUESTION_TEXT = "What are the security implications of storing organizational data in the public cloud?"
TARGET_CHUNK_IDS = [
    "NIST_SP_800-144_txt_00080",
    "NIST_SP_800-144_txt_00081",
    "NIST_SP_800-144_txt_00082",
]
TARGET_SET = set(TARGET_CHUNK_IDS)
FINAL_TOP_K = 5


# ============================================================================
# METRICS COMPUTATION (Pure Functional Implementation)
# ============================================================================

def compute_hit_rate(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    """Compute Hit Rate@K: 1.0 if at least one relevant chunk is in top-k, else 0.0."""
    if not ground_truth or k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    return 1.0 if any(cid in ground_truth for cid in top_k) else 0.0


def compute_recall(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    """Compute Recall@K: fraction of ground-truth chunks retrieved in top-k."""
    if not ground_truth or k <= 0:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    hits = len(top_k_set.intersection(ground_truth))
    return float(hits) / float(len(ground_truth))


def compute_precision(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    """Compute Precision@K: fraction of retrieved top-k chunks that are relevant."""
    if k <= 0:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    hits = len(top_k_set.intersection(ground_truth))
    return float(hits) / float(k)


def compute_mrr(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    """Compute Reciprocal Rank: 1 / rank of first relevant chunk, or 0.0 if not found within k."""
    if not ground_truth:
        return 0.0
    candidates = retrieved_ids[:k]
    for rank, cid in enumerate(candidates, start=1):
        if cid in ground_truth:
            return 1.0 / float(rank)
    return 0.0


def compute_ndcg(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    """Compute Normalized Discounted Cumulative Gain (NDCG@K) with binary relevance."""
    if not ground_truth or k <= 0:
        return 0.0

    dcg = 0.0
    for rank, cid in enumerate(retrieved_ids[:k], start=1):
        if cid in ground_truth:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(k, len(ground_truth))
    if ideal_hits == 0:
        return 0.0

    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return float(dcg / idcg) if idcg > 0 else 0.0


# ============================================================================
# EXPERIMENT RUNNER
# ============================================================================

def run_configuration(
    config_id: str,
    config_name: str,
    dense_depth: int,
    bm25_depth: int,
    rrf_pool: int,
    enable_reranker: bool,
    dense_retriever: DenseRetriever,
    bm25_retriever: BM25Retriever,
    rrf_fusion: RRFFusion,
    reranker: CrossEncoderReranker,
) -> Dict[str, Any]:
    """Execute a single controlled candidate-depth configuration on Q10."""
    print("\n" + "=" * 80)
    print(f"RUNNING CONFIGURATION {config_id}: {config_name}")
    print(f"Parameters: Dense={dense_depth}, BM25={bm25_depth}, RRF={rrf_pool}, Reranker={enable_reranker}")
    print("=" * 80)

    # 1. Dense Retrieval
    t0 = time.perf_counter()
    dense_candidates = dense_retriever.retrieve(QUESTION_TEXT, top_k=dense_depth)
    dense_latency_ms = (time.perf_counter() - t0) * 1000

    dense_map = {}
    for r, c in enumerate(dense_candidates, start=1):
        score_val = getattr(c, "dense_score", None) or getattr(c, "score", None)
        dense_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    # 2. BM25 Retrieval
    t0 = time.perf_counter()
    bm25_candidates = bm25_retriever.retrieve(QUESTION_TEXT, top_k=bm25_depth)
    bm25_latency_ms = (time.perf_counter() - t0) * 1000

    bm25_map = {}
    for r, c in enumerate(bm25_candidates, start=1):
        score_val = getattr(c, "bm25_score", None) or getattr(c, "score", None)
        bm25_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    # 3. RRF Fusion
    t0 = time.perf_counter()
    hybrid_candidates = rrf_fusion.fuse([dense_candidates, bm25_candidates], top_k=rrf_pool)
    rrf_latency_ms = (time.perf_counter() - t0) * 1000
    retrieval_latency_ms = dense_latency_ms + bm25_latency_ms + rrf_latency_ms

    rrf_map = {}
    for r, c in enumerate(hybrid_candidates, start=1):
        score_val = getattr(c, "rrf_score", None) or getattr(c, "score", None)
        rrf_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    # 4. Reranking / Final Selection
    rerank_map = {}
    reranking_latency_ms = 0.0

    if enable_reranker:
        t0 = time.perf_counter()
        # Rerank the entire fused candidate pool to observe full reranked distribution
        reranked_pool = reranker.rerank(QUESTION_TEXT, hybrid_candidates, top_n=len(hybrid_candidates))
        reranking_latency_ms = (time.perf_counter() - t0) * 1000

        for r, c in enumerate(reranked_pool, start=1):
            score_val = getattr(c, "reranker_score", None) or getattr(c, "score", None)
            rerank_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

        final_chunks = reranked_pool[:FINAL_TOP_K]
    else:
        # Without reranking: take top 5 directly from RRF pool
        final_chunks = hybrid_candidates[:FINAL_TOP_K]

    total_latency_ms = retrieval_latency_ms + reranking_latency_ms
    final_chunk_ids = [c.chunk_id for c in final_chunks]

    # Metrics on final delivered chunks (top 5)
    hit5 = compute_hit_rate(final_chunk_ids, TARGET_SET, k=FINAL_TOP_K)
    recall5 = compute_recall(final_chunk_ids, TARGET_SET, k=FINAL_TOP_K)
    precision5 = compute_precision(final_chunk_ids, TARGET_SET, k=FINAL_TOP_K)
    mrr5 = compute_mrr(final_chunk_ids, TARGET_SET, k=FINAL_TOP_K)
    ndcg5 = compute_ndcg(final_chunk_ids, TARGET_SET, k=FINAL_TOP_K)

    # Target chunk diagnostics
    target_diagnostics = {}
    for tid in TARGET_CHUNK_IDS:
        in_dense = tid in dense_map
        d_rank, d_score = dense_map.get(tid, (None, None))

        in_bm25 = tid in bm25_map
        b_rank, b_score = bm25_map.get(tid, (None, None))

        in_rrf = tid in rrf_map
        r_rank, r_score = rrf_map.get(tid, (None, None))

        in_rerank = tid in rerank_map
        rk_rank, rk_score = rerank_map.get(tid, (None, None))

        in_final_5 = tid in final_chunk_ids
        final_rank = (final_chunk_ids.index(tid) + 1) if in_final_5 else None

        target_diagnostics[tid] = {
            "chunk_id": tid,
            "in_dense": in_dense,
            "dense_rank": d_rank,
            "dense_score": round(d_score, 4) if d_score is not None else None,
            "in_bm25": in_bm25,
            "bm25_rank": b_rank,
            "bm25_score": round(b_score, 4) if b_score is not None else None,
            "in_rrf_pool": in_rrf,
            "rrf_rank": r_rank,
            "rrf_score": round(r_score, 6) if r_score is not None else None,
            "in_rerank_pool": in_rerank if enable_reranker else "N/A",
            "rerank_rank": rk_rank if enable_reranker else "N/A",
            "rerank_score": round(rk_score, 4) if (enable_reranker and rk_score is not None) else "N/A",
            "in_final_top5": in_final_5,
            "final_rank": final_rank,
        }

    # Format final chunks summary
    final_summary = []
    for rank, c in enumerate(final_chunks, start=1):
        meta = getattr(c, "metadata", {})
        sec = meta.section if hasattr(meta, "section") else meta.get("section", "Unknown")
        doc = meta.document_id if hasattr(meta, "document_id") else meta.get("document_id", "Unknown")
        score_val = (
            getattr(c, "reranker_score", None)
            if enable_reranker
            else getattr(c, "rrf_score", None)
        )
        final_summary.append({
            "rank": rank,
            "chunk_id": c.chunk_id,
            "document_id": doc,
            "section": sec,
            "score": round(float(score_val), 4) if score_val is not None else None,
            "is_target": c.chunk_id in TARGET_SET,
        })

    print(f"Results for Config {config_id}:")
    print(f"  Hit@5: {hit5:.2%} | Recall@5: {recall5:.2%} | MRR@5: {mrr5:.4f} | NDCG@5: {ndcg5:.4f}")
    print(f"  Retrieval Latency: {retrieval_latency_ms:.1f}ms | Rerank Latency: {reranking_latency_ms:.1f}ms | Total: {total_latency_ms:.1f}ms")
    print("  Final Top-5 Chunks:")
    for f in final_summary:
        mark = "🎯 [TARGET]" if f["is_target"] else "  "
        print(f"    {mark} Rank {f['rank']}: {f['chunk_id']} ({f['document_id']}) — score: {f['score']} — {f['section']}")

    return {
        "config_id": config_id,
        "config_name": config_name,
        "dense_depth": dense_depth,
        "bm25_depth": bm25_depth,
        "rrf_pool": rrf_pool,
        "enable_reranker": enable_reranker,
        "latencies_ms": {
            "dense": round(dense_latency_ms, 2),
            "bm25": round(bm25_latency_ms, 2),
            "rrf": round(rrf_latency_ms, 2),
            "retrieval_total": round(retrieval_latency_ms, 2),
            "reranking": round(reranking_latency_ms, 2),
            "end_to_end_total": round(total_latency_ms, 2),
        },
        "metrics": {
            "hit@5": hit5,
            "recall@5": recall5,
            "precision@5": precision5,
            "mrr@5": mrr5,
            "ndcg@5": ndcg5,
        },
        "target_diagnostics": target_diagnostics,
        "final_top5_chunks": final_summary,
    }


def format_markdown_report(results: Dict[str, Any]) -> str:
    """Format experiment results into a clean markdown report."""
    configs = results["configurations"]

    lines = [
        "# Controlled Candidate-Depth Retrieval Experiment on Question Q10",
        "",
        "- **Timestamp:** `" + results["metadata"]["timestamp"] + "`",
        "- **Question ID:** `Q10`",
        "- **Question:** *\"" + QUESTION_TEXT + "\"*",
        "- **Target Ground-Truth Chunks:** `NIST_SP_800-144_txt_00080`, `NIST_SP_800-144_txt_00081`, `NIST_SP_800-144_txt_00082`",
        "",
        "---",
        "",
        "## 1. Overall Performance Comparison Table",
        "",
        "| Configuration | Dense / BM25 / RRF Pool | Reranker | Hit@5 | Recall@5 | MRR@5 | NDCG@5 | Retrieval Latency | Rerank Latency | Total Latency |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for cid, c in configs.items():
        m = c["metrics"]
        lat = c["latencies_ms"]
        rerank_str = "Enabled" if c["enable_reranker"] else "Disabled"
        pool_str = f"{c['dense_depth']} / {c['bm25_depth']} / {c['rrf_pool']}"
        lines.append(
            f"| **{cid}. {c['config_name']}** | {pool_str} | {rerank_str} | "
            f"**{m['hit@5']:.1%}** | **{m['recall@5']:.1%}** | **{m['mrr@5']:.4f}** | **{m['ndcg@5']:.4f}** | "
            f"{lat['retrieval_total']:.1f} ms | {lat['reranking']:.1f} ms | {lat['end_to_end_total']:.1f} ms |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Target Ground-Truth Chunk Journey Across Pipeline Stages",
        "",
        "### A. Baseline (Dense 20 / BM25 20 / RRF 20 -> Reranker -> Top 5)",
        "",
        "| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker (Rank / Score) | In Final Top 5? |",
        "|---|---|---|---|---|---|",
    ])

    for tid in TARGET_CHUNK_IDS:
        diag = configs["A"]["target_diagnostics"][tid]
        d_str = f"Rank {diag['dense_rank']} ({diag['dense_score']})" if diag["in_dense"] else "❌ Outside 20"
        b_str = f"Rank {diag['bm25_rank']} ({diag['bm25_score']})" if diag["in_bm25"] else "❌ Outside 20"
        r_str = f"Rank {diag['rrf_rank']} ({diag['rrf_score']})" if diag["in_rrf_pool"] else "❌ Truncated (< 20)"
        rk_str = f"Rank {diag['rerank_rank']} ({diag['rerank_score']})" if diag["in_rerank_pool"] != "N/A" and diag["rerank_rank"] != "N/A" else "❌ Not seen"
        f_str = f"✅ Rank {diag['final_rank']}" if diag["in_final_top5"] else "❌ No"
        lines.append(f"| `{tid}` | {d_str} | {b_str} | {r_str} | {rk_str} | {f_str} |")

    lines.extend([
        "",
        "### B. Expanded Retrieval (Dense 30 / BM25 30 / RRF 30 -> Reranker -> Top 5)",
        "",
        "| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker (Rank / Score) | In Final Top 5? |",
        "|---|---|---|---|---|---|",
    ])

    for tid in TARGET_CHUNK_IDS:
        diag = configs["B"]["target_diagnostics"][tid]
        d_str = f"Rank {diag['dense_rank']} ({diag['dense_score']})" if diag["in_dense"] else "❌ Outside 30"
        b_str = f"Rank {diag['bm25_rank']} ({diag['bm25_score']})" if diag["in_bm25"] else "❌ Outside 30"
        r_str = f"Rank {diag['rrf_rank']} ({diag['rrf_score']})" if diag["in_rrf_pool"] else "❌ Truncated (< 30)"
        rk_str = f"Rank {diag['rerank_rank']} ({diag['rerank_score']})" if diag["in_rerank_pool"] != "N/A" and diag["rerank_rank"] != "N/A" else "❌ Not seen"
        f_str = f"✅ Rank {diag['final_rank']}" if diag["in_final_top5"] else "❌ No"
        lines.append(f"| `{tid}` | {d_str} | {b_str} | {r_str} | {rk_str} | {f_str} |")

    lines.extend([
        "",
        "### C. Larger Candidate Pool (Dense 50 / BM25 50 / RRF 50 -> Reranker -> Top 5)",
        "",
        "| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker (Rank / Score) | In Final Top 5? |",
        "|---|---|---|---|---|---|",
    ])

    for tid in TARGET_CHUNK_IDS:
        diag = configs["C"]["target_diagnostics"][tid]
        d_str = f"Rank {diag['dense_rank']} ({diag['dense_score']})" if diag["in_dense"] else "❌ Outside 50"
        b_str = f"Rank {diag['bm25_rank']} ({diag['bm25_score']})" if diag["in_bm25"] else "❌ Outside 50"
        r_str = f"Rank {diag['rrf_rank']} ({diag['rrf_score']})" if diag["in_rrf_pool"] else "❌ Truncated (< 50)"
        rk_str = f"Rank {diag['rerank_rank']} ({diag['rerank_score']})" if diag["in_rerank_pool"] != "N/A" and diag["rerank_rank"] != "N/A" else "❌ Not seen"
        f_str = f"✅ Rank {diag['final_rank']}" if diag["in_final_top5"] else "❌ No"
        lines.append(f"| `{tid}` | {d_str} | {b_str} | {r_str} | {rk_str} | {f_str} |")

    lines.extend([
        "",
        "### D. Larger Candidate Pool Without Reranking (Dense 50 / BM25 50 / RRF 50 -> Top 5 Direct)",
        "",
        "| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker | In Final Top 5? |",
        "|---|---|---|---|---|---|",
    ])

    for tid in TARGET_CHUNK_IDS:
        diag = configs["D"]["target_diagnostics"][tid]
        d_str = f"Rank {diag['dense_rank']} ({diag['dense_score']})" if diag["in_dense"] else "❌ Outside 50"
        b_str = f"Rank {diag['bm25_rank']} ({diag['bm25_score']})" if diag["in_bm25"] else "❌ Outside 50"
        r_str = f"Rank {diag['rrf_rank']} ({diag['rrf_score']})" if diag["in_rrf_pool"] else "❌ Truncated (< 50)"
        rk_str = "Disabled"
        f_str = f"✅ Rank {diag['final_rank']}" if diag["in_final_top5"] else "❌ No"
        lines.append(f"| `{tid}` | {d_str} | {b_str} | {r_str} | {rk_str} | {f_str} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Actual Delivered Top-5 Chunks by Configuration",
        "",
    ])

    for cid, c in configs.items():
        lines.append(f"### Configuration {cid}: {c['config_name']}")
        for f in c["final_top5_chunks"]:
            mark = "🎯 **[TARGET CHUNK]**" if f["is_target"] else "⚪"
            score_type = "Reranker Score" if c["enable_reranker"] else "RRF Score"
            lines.append(f"{f['rank']}. {mark} `{f['chunk_id']}` ({f['document_id']}) — *{score_type}: {f['score']}* — Section: `{f['section']}`")
        lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 80)
    print("CONTROLLED CANDIDATE-DEPTH EXPERIMENT (QUESTION Q10)")
    print("=" * 80)

    # 1. Warm up and initialize components
    print("\n[Step 1/3] Initializing and warming up models...")
    t_start = time.perf_counter()
    dense_retriever = DenseRetriever()
    bm25_retriever = BM25Retriever()
    rrf_fusion = RRFFusion(k=settings.rrf_k)
    reranker = CrossEncoderReranker()

    dense_retriever._ensure_initialized()
    bm25_retriever._ensure_initialized()
    reranker._ensure_initialized()
    print(f"Components warmed up in {(time.perf_counter() - t_start):.2f}s")

    # 2. Run the four experiment configurations
    print("\n[Step 2/3] Executing 4 candidate-depth configurations...")

    configs_to_run = [
        ("A", "Baseline (Dense 20 / BM25 20 / RRF 20 -> Reranker)", 20, 20, 20, True),
        ("B", "Expanded Retrieval (Dense 30 / BM25 30 / RRF 30 -> Reranker)", 30, 30, 30, True),
        ("C", "Larger Candidate Pool (Dense 50 / BM25 50 / RRF 50 -> Reranker)", 50, 50, 50, True),
        ("D", "Larger Candidate Pool Without Reranking (Dense 50 / BM25 50 / RRF 50)", 50, 50, 50, False),
    ]

    experiment_results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "question_id": QUESTION_ID,
            "question": QUESTION_TEXT,
            "ground_truth_chunks": TARGET_CHUNK_IDS,
            "final_top_k": FINAL_TOP_K,
        },
        "configurations": {},
    }

    for cid, cname, d_k, b_k, r_k, rk_on in configs_to_run:
        res = run_configuration(
            config_id=cid,
            config_name=cname,
            dense_depth=d_k,
            bm25_depth=b_k,
            rrf_pool=r_k,
            enable_reranker=rk_on,
            dense_retriever=dense_retriever,
            bm25_retriever=bm25_retriever,
            rrf_fusion=rrf_fusion,
            reranker=reranker,
        )
        experiment_results["configurations"][cid] = res

    # 3. Persist Experimental Artifacts
    print("\n[Step 3/3] Saving experimental reports...")
    out_dir = PROJECT_ROOT / "reports" / "retrieval_evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "experiment_q10_candidate_depth.json"
    md_path = out_dir / "experiment_q10_candidate_depth.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(experiment_results, f, indent=2)

    md_content = format_markdown_report(experiment_results)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Saved experiment JSON report: {json_path}")
    print(f"Saved experiment Markdown report: {md_path}")
    print("\nExperiment completed successfully.")


if __name__ == "__main__":
    main()
