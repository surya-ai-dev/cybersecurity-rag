"""Controlled 36-Question Retrieval Benchmark: Cross-Encoder Query Alignment Verification.

Compares:
  1. Config A: Baseline (Original standalone query throughout)
  2. Config D-Coupled (Previous Phase 4B: Rewritten query used for candidate retrieval AND Cross-Encoder reranking)
  3. Config D-Decoupled (Current Phase 4B Fix: Rewritten query used for candidate retrieval, original standalone question preserved for Cross-Encoder reranking)

Generates:
  reports/retrieval_evaluation/benchmark_cross_encoder_alignment.json
  reports/retrieval_evaluation/benchmark_cross_encoder_alignment.md
"""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.models import RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.confidence import ConfidenceEvaluator, merge_candidate_pools
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import RRFFusion

RETRIEVAL_TOP_K = 20
RRF_POOL_TOP_K = 20
FINAL_TOP_K = 5


def compute_hit_rate(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    if not ground_truth or k <= 0:
        return 0.0
    return 1.0 if any(cid in ground_truth for cid in retrieved_ids[:k]) else 0.0


def compute_recall(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    if not ground_truth or k <= 0:
        return 0.0
    hits = len(set(retrieved_ids[:k]).intersection(ground_truth))
    return float(hits) / float(len(ground_truth))


def compute_precision(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    if k <= 0:
        return 0.0
    hits = len(set(retrieved_ids[:k]).intersection(ground_truth))
    return float(hits) / float(k)


def compute_mrr(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
    if not ground_truth:
        return 0.0
    for rank, cid in enumerate(retrieved_ids[:k], start=1):
        if cid in ground_truth:
            return 1.0 / float(rank)
    return 0.0


def compute_ndcg(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int = FINAL_TOP_K) -> float:
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
    return dcg / idcg


def compute_all_metrics(retrieved_ids: Sequence[str], ground_truth: Set[str]) -> Dict[str, float]:
    return {
        "hit@1": round(compute_hit_rate(retrieved_ids, ground_truth, k=1), 4),
        "hit@5": round(compute_hit_rate(retrieved_ids, ground_truth, k=5), 4),
        "recall@5": round(compute_recall(retrieved_ids, ground_truth, k=5), 4),
        "precision@5": round(compute_precision(retrieved_ids, ground_truth, k=5), 4),
        "mrr@5": round(compute_mrr(retrieved_ids, ground_truth, k=5), 4),
        "ndcg@5": round(compute_ndcg(retrieved_ids, ground_truth, k=5), 4),
    }


def main():
    print("=" * 80)
    print("CONTROLLED 36-QUESTION BENCHMARK: CROSS-ENCODER QUERY ALIGNMENT")
    print("=" * 80)

    gt_path = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_v2.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth_data = json.load(f)

    rewriter_report_path = PROJECT_ROOT / "reports" / "retrieval_evaluation" / "experiment_36q_revised_rewriter.json"
    cached_rewrites: Dict[str, str] = {}
    if rewriter_report_path.exists():
        with open(rewriter_report_path, "r", encoding="utf-8") as f:
            prev_rep = json.load(f)
            for item in prev_rep.get("per_question_results", []):
                cached_rewrites[item["question_id"]] = item["rewritten_question"]
        print(f"Loaded {len(cached_rewrites)} pre-computed rewritten queries.")
    else:
        print("Warning: Cached rewritten queries not found.")

    print("\nInitializing retrieval components...")
    t_start = time.perf_counter()
    dense = DenseRetriever()
    bm25 = BM25Retriever()
    rrf = RRFFusion(k=settings.rrf_k)
    reranker = CrossEncoderReranker()
    evaluator = ConfidenceEvaluator(
        score_threshold=settings.adaptive_confidence_threshold,
        mean_threshold=settings.adaptive_confidence_mean_threshold,
    )

    # Warmup
    _ = dense.retrieve("warmup", top_k=2)
    _ = bm25.retrieve("warmup", top_k=2)
    warmup_pool = rrf.fuse([dense.retrieve("warmup", top_k=2), bm25.retrieve("warmup", top_k=2)], top_k=2)
    _ = reranker.rerank("warmup", warmup_pool, top_n=2)
    _ = evaluator.evaluate(warmup_pool)
    print(f"Warmup complete in {(time.perf_counter() - t_start):.2f}s.")

    question_keys = list(ground_truth_data.keys())
    per_question_results = []

    for idx, qid in enumerate(question_keys, start=1):
        qdata = ground_truth_data[qid]
        orig_q = qdata["question"]
        gt_set = set(qdata["relevant_chunks"])
        rewritten_q = cached_rewrites.get(qid, orig_q)

        # 1. Initial Pass
        t0 = time.perf_counter()
        init_d = dense.retrieve(orig_q, top_k=RETRIEVAL_TOP_K)
        init_b = bm25.retrieve(orig_q, top_k=RETRIEVAL_TOP_K)
        init_pool = rrf.fuse([init_d, init_b], top_k=RRF_POOL_TOP_K)
        t_init = (time.perf_counter() - t0) * 1000

        # Confidence Evaluation
        conf = evaluator.evaluate(init_pool)

        # Baseline (Config A)
        t0 = time.perf_counter()
        reranked_A = reranker.rerank(orig_q, init_pool, top_n=RRF_POOL_TOP_K)
        t_rerank_A = (time.perf_counter() - t0) * 1000
        top5_A = [c.chunk_id for c in reranked_A[:FINAL_TOP_K]]
        metrics_A = compute_all_metrics(top5_A, gt_set)

        # 2. Rewritten Pass (if needed by adaptive)
        if conf.is_confident:
            metrics_coupled = metrics_A
            top5_coupled = top5_A
            t_coupled = t_init + t_rerank_A

            metrics_decoupled = metrics_A
            top5_decoupled = top5_A
            t_decoupled = t_init + t_rerank_A
            rewrite_triggered = False
            merged_pool_ids = [c.chunk_id for c in init_pool]
        else:
            rewrite_triggered = True
            t0 = time.perf_counter()
            rewr_d = dense.retrieve(rewritten_q, top_k=RETRIEVAL_TOP_K)
            rewr_b = bm25.retrieve(rewritten_q, top_k=RETRIEVAL_TOP_K)
            rewr_pool = rrf.fuse([rewr_d, rewr_b], top_k=RRF_POOL_TOP_K)
            t_rewr = (time.perf_counter() - t0) * 1000

            merged = merge_candidate_pools(init_pool, rewr_pool, limit=RRF_POOL_TOP_K)
            merged_pool_ids = [c.chunk_id for c in merged]

            # Coupled Rerank (Old Phase 4B: Reranker gets rewritten_q)
            t0 = time.perf_counter()
            reranked_coupled = reranker.rerank(rewritten_q, merged, top_n=RRF_POOL_TOP_K)
            t_rerank_c = (time.perf_counter() - t0) * 1000
            top5_coupled = [c.chunk_id for c in reranked_coupled[:FINAL_TOP_K]]
            metrics_coupled = compute_all_metrics(top5_coupled, gt_set)
            t_coupled = t_init + t_rewr + t_rerank_c

            # Decoupled Rerank (Fixed Phase 4B: Reranker gets orig_q)
            t0 = time.perf_counter()
            reranked_decoupled = reranker.rerank(orig_q, merged, top_n=RRF_POOL_TOP_K)
            t_rerank_d = (time.perf_counter() - t0) * 1000
            top5_decoupled = [c.chunk_id for c in reranked_decoupled[:FINAL_TOP_K]]
            metrics_decoupled = compute_all_metrics(top5_decoupled, gt_set)
            t_decoupled = t_init + t_rewr + t_rerank_d

        per_question_results.append({
            "question_id": qid,
            "question": orig_q,
            "rewritten_question": rewritten_q,
            "expected_chunks": list(gt_set),
            "rewrite_triggered": rewrite_triggered,
            "confidence_reason": conf.reason,
            "baseline": {
                "top5": top5_A,
                "metrics": metrics_A,
                "latency_ms": round(t_init + t_rerank_A, 2),
            },
            "coupled": {
                "top5": top5_coupled,
                "metrics": metrics_coupled,
                "latency_ms": round(t_coupled, 2),
            },
            "decoupled": {
                "top5": top5_decoupled,
                "metrics": metrics_decoupled,
                "latency_ms": round(t_decoupled, 2),
            },
        })
        print(f"[{idx:02d}/36] {qid} | Trig: {rewrite_triggered} | Base Hit@5: {metrics_A['hit@5']} | Coupled: {metrics_coupled['hit@5']} | Decoupled: {metrics_decoupled['hit@5']}")

    # Aggregates
    def aggregate(config_key: str) -> Dict[str, float]:
        n = len(per_question_results)
        return {
            "hit@1": round(sum(r[config_key]["metrics"]["hit@1"] for r in per_question_results) / n * 100, 2),
            "hit@5": round(sum(r[config_key]["metrics"]["hit@5"] for r in per_question_results) / n * 100, 2),
            "recall@5": round(sum(r[config_key]["metrics"]["recall@5"] for r in per_question_results) / n * 100, 2),
            "precision@5": round(sum(r[config_key]["metrics"]["precision@5"] for r in per_question_results) / n * 100, 2),
            "mrr@5": round(sum(r[config_key]["metrics"]["mrr@5"] for r in per_question_results) / n, 4),
            "ndcg@5": round(sum(r[config_key]["metrics"]["ndcg@5"] for r in per_question_results) / n, 4),
            "latency_ms": round(sum(r[config_key]["latency_ms"] for r in per_question_results) / n, 1),
        }

    agg_base = aggregate("baseline")
    agg_coupled = aggregate("coupled")
    agg_decoupled = aggregate("decoupled")

    output_dir = PROJECT_ROOT / "reports" / "retrieval_evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "benchmark_cross_encoder_alignment.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "aggregates": {
                "baseline": agg_base,
                "coupled": agg_coupled,
                "decoupled": agg_decoupled,
            },
            "per_question_results": per_question_results,
        }, f, indent=2)

    # Markdown report
    md_path = output_dir / "benchmark_cross_encoder_alignment.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Cross-Encoder Query Alignment Benchmark Report\n\n")
        f.write(f"Generated at: {datetime.utcnow().isoformat()}\n\n")
        f.write("## 1. Aggregate Comparison\n\n")
        f.write("| Configuration | Hit@1 (%) | Hit@5 (%) | Recall@5 (%) | Precision@5 (%) | MRR@5 | NDCG@5 | Latency (ms) |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        f.write(f"| **Config A: Baseline (No Rewrite)** | {agg_base['hit@1']}% | {agg_base['hit@5']}% | {agg_base['recall@5']}% | {agg_base['precision@5']}% | {agg_base['mrr@5']} | {agg_base['ndcg@5']} | {agg_base['latency_ms']} ms |\n")
        f.write(f"| **Config D-Coupled (Previous Phase 4B)** | {agg_coupled['hit@1']}% | {agg_coupled['hit@5']}% | {agg_coupled['recall@5']}% | {agg_coupled['precision@5']}% | {agg_coupled['mrr@5']} | {agg_coupled['ndcg@5']} | {agg_coupled['latency_ms']} ms |\n")
        f.write(f"| **Config D-Decoupled (Phase 4B Fixed)** | {agg_decoupled['hit@1']}% | {agg_decoupled['hit@5']}% | {agg_decoupled['recall@5']}% | {agg_decoupled['precision@5']}% | {agg_decoupled['mrr@5']} | {agg_decoupled['ndcg@5']} | {agg_decoupled['latency_ms']} ms |\n\n")

        f.write("## 2. Target Regressed & Improved Questions Focus\n\n")
        f.write("| QID | Original Question | Baseline Hit@5 | Coupled Hit@5 | Decoupled Hit@5 | Status |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: | :--- |\n")
        focus_qids = ["Q4", "Q11", "Q12", "Q17", "Q30", "Q10", "Q19", "Q25", "Q38", "Q40"]
        for r in per_question_results:
            if r["question_id"] in focus_qids:
                h_b = int(r["baseline"]["metrics"]["hit@5"])
                h_c = int(r["coupled"]["metrics"]["hit@5"])
                h_d = int(r["decoupled"]["metrics"]["hit@5"])
                status = "RESTORED" if (h_c == 0 and h_d == 1) else ("RETAINED IMPROVEMENT" if (h_b == 0 and h_d == 1) else "UNCHANGED")
                f.write(f"| **{r['question_id']}** | {r['question'][:50]}... | {h_b} | {h_c} | {h_d} | {status} |\n")

    print("\nBenchmark complete! Results written to:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")


if __name__ == "__main__":
    main()
