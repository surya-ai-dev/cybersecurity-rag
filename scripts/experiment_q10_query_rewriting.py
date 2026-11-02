"""Controlled Query Rewriting Retrieval Experiment on Question Q10.

Evaluates whether technical cybersecurity query rewriting improves Q10 retrieval
under identical candidate-depth settings (Dense=50, BM25=50, RRF=50, Reranker=True, Top=5).

Configurations Tested:
  A. Baseline:
     Original question: "What are the security implications of storing organizational data in the public cloud?"
  B1. Automated LLM Rewriter (QueryRewriter / qwen/qwen3.8-27b via Groq):
     "public cloud data storage security implications organizational data confidentiality integrity availability"
  B2. Domain-Expanded Technical Search Query:
     "public cloud data storage security implications data protection shared environment multi-tenant isolation data at rest encryption"

Reports Generated:
  reports/retrieval_evaluation/experiment_q10_query_rewriting.json
  reports/retrieval_evaluation/experiment_q10_query_rewriting.md
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
from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import RRFFusion

# Constants for Q10
QUESTION_ID = "Q10"
ORIGINAL_QUESTION = "What are the security implications of storing organizational data in the public cloud?"
TARGET_CHUNK_IDS = [
    "NIST_SP_800-144_txt_00080",
    "NIST_SP_800-144_txt_00081",
    "NIST_SP_800-144_txt_00082",
]
TARGET_SET = set(TARGET_CHUNK_IDS)

# Fixed Experimental Settings across all runs
RETRIEVAL_TOP_K = 50
RRF_POOL_TOP_K = 50
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

def run_retrieval_pipeline(
    exp_id: str,
    exp_name: str,
    search_query: str,
    original_query: str,
    rewriter_latency_ms: float,
    dense_retriever: DenseRetriever,
    bm25_retriever: BM25Retriever,
    rrf_fusion: RRFFusion,
    reranker: CrossEncoderReranker,
) -> Dict[str, Any]:
    """Execute pipeline for a specific query under depth-50 settings."""
    print("\n" + "=" * 80)
    print(f"RUNNING EXPERIMENT {exp_id}: {exp_name}")
    print(f"Search Query: \"{search_query}\"")
    print("=" * 80)

    # 1. Dense Retrieval (top_k=50)
    t0 = time.perf_counter()
    dense_candidates = dense_retriever.retrieve(search_query, top_k=RETRIEVAL_TOP_K)
    dense_latency_ms = (time.perf_counter() - t0) * 1000

    dense_map = {}
    for r, c in enumerate(dense_candidates, start=1):
        score_val = getattr(c, "dense_score", None) or getattr(c, "score", None)
        dense_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    # 2. BM25 Retrieval (top_k=50)
    t0 = time.perf_counter()
    bm25_candidates = bm25_retriever.retrieve(search_query, top_k=RETRIEVAL_TOP_K)
    bm25_latency_ms = (time.perf_counter() - t0) * 1000

    bm25_map = {}
    for r, c in enumerate(bm25_candidates, start=1):
        score_val = getattr(c, "bm25_score", None) or getattr(c, "score", None)
        bm25_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    # 3. RRF Fusion (pool=50)
    t0 = time.perf_counter()
    hybrid_candidates = rrf_fusion.fuse([dense_candidates, bm25_candidates], top_k=RRF_POOL_TOP_K)
    rrf_latency_ms = (time.perf_counter() - t0) * 1000
    retrieval_latency_ms = dense_latency_ms + bm25_latency_ms + rrf_latency_ms

    rrf_map = {}
    for r, c in enumerate(hybrid_candidates, start=1):
        score_val = getattr(c, "rrf_score", None) or getattr(c, "score", None)
        rrf_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    # 4. Cross-Encoder Reranker
    # Note: CrossEncoder is queried with the search query against candidate chunks
    t0 = time.perf_counter()
    reranked_pool = reranker.rerank(search_query, hybrid_candidates, top_n=len(hybrid_candidates))
    reranking_latency_ms = (time.perf_counter() - t0) * 1000

    rerank_map = {}
    for r, c in enumerate(reranked_pool, start=1):
        score_val = getattr(c, "reranker_score", None) or getattr(c, "score", None)
        rerank_map[c.chunk_id] = (r, float(score_val) if score_val is not None else 0.0)

    final_chunks = reranked_pool[:FINAL_TOP_K]
    final_chunk_ids = [c.chunk_id for c in final_chunks]
    total_latency_ms = rewriter_latency_ms + retrieval_latency_ms + reranking_latency_ms

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

        # Stage status explanation
        if in_final_5:
            stage_status = f"Retained in Final Top 5 (Rank {final_rank})"
        elif in_rerank:
            stage_status = f"Retrieved in candidate pool but ranked outside Top 5 by Reranker (Rank {rk_rank})"
        elif in_rrf:
            stage_status = f"Present in RRF pool (Rank {r_rank})"
        elif in_dense or in_bm25:
            stage_status = "Discarded during RRF top-50 pool cutoff"
        else:
            stage_status = "Absent from both Dense and BM25 top 50"

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
            "in_rerank_pool": in_rerank,
            "rerank_rank": rk_rank,
            "rerank_score": round(rk_score, 4) if rk_score is not None else None,
            "in_final_top5": in_final_5,
            "final_rank": final_rank,
            "stage_status": stage_status,
        }

    # Format final chunks summary
    final_summary = []
    for rank, c in enumerate(final_chunks, start=1):
        meta = getattr(c, "metadata", {})
        sec = meta.section if hasattr(meta, "section") else meta.get("section", "Unknown")
        doc = meta.document_id if hasattr(meta, "document_id") else meta.get("document_id", "Unknown")
        score_val = getattr(c, "reranker_score", None)
        final_summary.append({
            "rank": rank,
            "chunk_id": c.chunk_id,
            "document_id": doc,
            "section": sec,
            "score": round(float(score_val), 4) if score_val is not None else None,
            "is_target": c.chunk_id in TARGET_SET,
        })

    print(f"Results for Experiment {exp_id}:")
    print(f"  Hit@5: {hit5:.2%} | Recall@5: {recall5:.2%} | MRR@5: {mrr5:.4f} | NDCG@5: {ndcg5:.4f}")
    print(f"  Rewriter: {rewriter_latency_ms:.1f}ms | Retrieval: {retrieval_latency_ms:.1f}ms | Rerank: {reranking_latency_ms:.1f}ms | Total: {total_latency_ms:.1f}ms")
    print("  Final Top-5 Chunks:")
    for f in final_summary:
        mark = "[TARGET]" if f["is_target"] else "        "
        print(f"    {mark} Rank {f['rank']}: {f['chunk_id']} ({f['document_id']}) - score: {f['score']} - {f['section']}")

    return {
        "experiment_id": exp_id,
        "experiment_name": exp_name,
        "original_query": original_query,
        "search_query": search_query,
        "settings": {
            "dense_depth": RETRIEVAL_TOP_K,
            "bm25_depth": RETRIEVAL_TOP_K,
            "rrf_pool": RRF_POOL_TOP_K,
            "final_top_k": FINAL_TOP_K,
        },
        "latencies_ms": {
            "query_rewriter": round(rewriter_latency_ms, 2),
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
    """Format full experiment into an executive markdown report."""
    configs = results["experiments"]

    lines = [
        "# Controlled Query Rewriting Experiment on Question Q10",
        "",
        "- **Timestamp:** `" + results["metadata"]["timestamp"] + "`",
        "- **Question ID:** `Q10`",
        "- **Original Question:** *\"" + ORIGINAL_QUESTION + "\"*",
        "- **Target Ground-Truth Chunks:** `NIST_SP_800-144_txt_00080`, `NIST_SP_800-144_txt_00081`, `NIST_SP_800-144_txt_00082`",
        "- **Fixed Candidate Depth Settings:** `Dense=50, BM25=50, RRF=50, Cross-Encoder=ms-marco-MiniLM-L-6-v2, Top=5`",
        "",
        "---",
        "",
        "## 1. Overall Performance Comparison Matrix",
        "",
        "| Experiment | Search Query Sent to Retrievers | Hit@5 | Recall@5 | MRR@5 | NDCG@5 | Rewriter Latency | Retrieval Latency | Rerank Latency | Total Latency |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for eid, e in configs.items():
        m = e["metrics"]
        lat = e["latencies_ms"]
        lines.append(
            f"| **{eid}. {e['experiment_name']}** | *\"{e['search_query']}\"* | "
            f"**{m['hit@5']:.1%}** | **{m['recall@5']:.1%}** | **{m['mrr@5']:.4f}** | **{m['ndcg@5']:.4f}** | "
            f"{lat['query_rewriter']:.1f} ms | {lat['retrieval_total']:.1f} ms | {lat['reranking']:.1f} ms | {lat['end_to_end_total']:.1f} ms |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Stage-by-Stage Target Chunk Tracking",
        "",
    ])

    for eid, e in configs.items():
        lines.append(f"### Experiment {eid}: {e['experiment_name']}")
        lines.append(f"- **Query Used:** *\"{e['search_query']}\"*")
        lines.append("")
        lines.append("| Target Chunk ID | Dense (Rank / Score) | BM25 (Rank / Score) | RRF Pool (Rank / Score) | Reranker (Rank / Score) | In Top 5? | Status / Fate |")
        lines.append("|---|---|---|---|---|---|---|")

        for tid in TARGET_CHUNK_IDS:
            diag = e["target_diagnostics"][tid]
            d_str = f"Rank {diag['dense_rank']} ({diag['dense_score']})" if diag["in_dense"] else "❌ > 50"
            b_str = f"Rank {diag['bm25_rank']} ({diag['bm25_score']})" if diag["in_bm25"] else "❌ > 50"
            r_str = f"Rank {diag['rrf_rank']} ({diag['rrf_score']})" if diag["in_rrf_pool"] else "❌ Discarded"
            rk_str = f"Rank {diag['rerank_rank']} ({diag['rerank_score']})" if diag["in_rerank_pool"] else "❌ Not seen"
            f_str = f"✅ Rank {diag['final_rank']}" if diag["in_final_top5"] else "❌ No"
            lines.append(f"| `{tid}` | {d_str} | {b_str} | {r_str} | {rk_str} | {f_str} | {diag['stage_status']} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Actual Delivered Top-5 Chunks by Experiment",
        "",
    ])

    for eid, e in configs.items():
        lines.append(f"### Experiment {eid}: {e['experiment_name']}")
        for f in e["final_top5_chunks"]:
            mark = "🎯 **[TARGET CHUNK]**" if f["is_target"] else "⚪"
            lines.append(f"{f['rank']}. {mark} `{f['chunk_id']}` ({f['document_id']}) — *Score: {f['score']}* — Section: `{f['section']}`")
        lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 80)
    print("CONTROLLED QUERY REWRITING EXPERIMENT (QUESTION Q10)")
    print("=" * 80)

    # 1. Warm up retrievers and models
    print("\n[Step 1/4] Initializing and warming up models...")
    t_start = time.perf_counter()
    dense_retriever = DenseRetriever()
    bm25_retriever = BM25Retriever()
    rrf_fusion = RRFFusion(k=settings.rrf_k)
    reranker = CrossEncoderReranker()

    dense_retriever._ensure_initialized()
    bm25_retriever._ensure_initialized()
    reranker._ensure_initialized()
    print(f"Models initialized in {(time.perf_counter() - t_start):.2f}s")

    # 2. Generate Automated Query Rewrite
    print("\n[Step 2/4] Generating automated query rewrite using QueryRewriter...")
    rewriter = QueryRewriter(enabled=True)
    rewrite_res = rewriter.rewrite(ORIGINAL_QUESTION)

    if rewrite_res.success and not rewrite_res.fallback_used and rewrite_res.rewritten_query:
        automated_query = rewrite_res.rewritten_query
        rewriter_latency_ms = rewrite_res.latency_ms
        print(f"Rewriter SUCCESS in {rewriter_latency_ms:.1f}ms: \"{automated_query}\"")
    else:
        automated_query = ORIGINAL_QUESTION
        rewriter_latency_ms = 0.0
        print(f"Rewriter FALLBACK used: {rewrite_res.error_message}")

    # Domain-Expanded technical query
    technical_query = (
        "public cloud data storage security implications data protection "
        "shared environment multi-tenant isolation data at rest encryption"
    )

    experiments_to_run = [
        ("A", "Baseline (Original Question)", ORIGINAL_QUESTION, 0.0),
        ("B1", "Automated LLM Rewriter (qwen/qwen3.8-27b)", automated_query, rewriter_latency_ms),
        ("B2", "Domain-Expanded Technical Query", technical_query, 0.0),
    ]

    experiment_results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "question_id": QUESTION_ID,
            "original_question": ORIGINAL_QUESTION,
            "ground_truth_chunks": TARGET_CHUNK_IDS,
            "settings": {
                "dense_top_k": RETRIEVAL_TOP_K,
                "bm25_top_k": RETRIEVAL_TOP_K,
                "rrf_pool_k": RRF_POOL_TOP_K,
                "final_top_k": FINAL_TOP_K,
                "reranker_model": reranker.model_name,
                "embedding_model": dense_retriever.embedding_model_name,
            },
        },
        "experiments": {},
    }

    # 3. Execute Experiments
    print("\n[Step 3/4] Running controlled experiments under identical depth-50 settings...")
    for eid, ename, q_str, rw_lat in experiments_to_run:
        res = run_retrieval_pipeline(
            exp_id=eid,
            exp_name=ename,
            search_query=q_str,
            original_query=ORIGINAL_QUESTION,
            rewriter_latency_ms=rw_lat,
            dense_retriever=dense_retriever,
            bm25_retriever=bm25_retriever,
            rrf_fusion=rrf_fusion,
            reranker=reranker,
        )
        experiment_results["experiments"][eid] = res

    # 4. Save Reports
    print("\n[Step 4/4] Writing experiment reports...")
    out_dir = PROJECT_ROOT / "reports" / "retrieval_evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "experiment_q10_query_rewriting.json"
    md_path = out_dir / "experiment_q10_query_rewriting.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(experiment_results, f, indent=2)

    md_content = format_markdown_report(experiment_results)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Saved experiment JSON report: {json_path}")
    print(f"Saved experiment Markdown report: {md_path}")
    print("\nQuery rewriting experiment completed successfully.")


if __name__ == "__main__":
    main()
