"""Calibration Experiment for ConfidenceEvaluator in Cybersecurity RAG.

Extracts dense score distributions, BM25 signals, exact identifier matches,
and initial retrieval metrics across all 36 questions in
data/evaluation/retrieval_ground_truth_v2.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.models import RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.confidence import extract_dense_score
from app.retrieval.dense import DenseRetriever
from app.retrieval.rrf import RRFFusion

RETRIEVAL_TOP_K = 20
RRF_POOL_TOP_K = 20


def extract_sorted_dense_scores(candidates: List[RetrievedChunk]) -> List[float]:
    """Extract valid dense scores and sort them descending (Issue 3 fix)."""
    scores = []
    for c in candidates:
        s = extract_dense_score(c)
        if s is not None:
            scores.append(s)
    scores.sort(reverse=True)
    return scores


def main():
    print("=" * 80)
    print("STEP 1: EXTRACTING RETRIEVAL SCORE DISTRIBUTIONS ACROSS ALL 36 QUESTIONS")
    print("=" * 80)

    gt_path = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_v2.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth_data = json.load(f)

    dense_retriever = DenseRetriever()
    bm25_retriever = BM25Retriever()
    rrf_fusion = RRFFusion(k=settings.rrf_k)

    # Warmup
    _ = dense_retriever.retrieve("warmup", top_k=2)
    _ = bm25_retriever.retrieve("warmup", top_k=2)

    results = []

    for qid, qdata in ground_truth_data.items():
        query = qdata["question"]
        gt_chunks = set(qdata["relevant_chunks"])

        dense_cands = dense_retriever.retrieve(query, top_k=RETRIEVAL_TOP_K)
        bm25_cands = bm25_retriever.retrieve(query, top_k=RETRIEVAL_TOP_K)
        fused_cands = rrf_fusion.fuse([dense_cands, bm25_cands], top_k=RRF_POOL_TOP_K)

        # 1. Independent sorted dense scores
        sorted_dense = extract_sorted_dense_scores(fused_cands)
        top1_dense = sorted_dense[0] if sorted_dense else None
        mean3_dense = (sum(sorted_dense[:3]) / 3.0) if len(sorted_dense) >= 3 else None
        mean5_dense = (sum(sorted_dense[:5]) / 5.0) if len(sorted_dense) >= 5 else None

        # 2. Old RRF-dependent dense scores (to measure Issue 3 mismatch)
        rrf_ordered_dense = []
        for c in fused_cands:
            s = extract_dense_score(c)
            if s is not None:
                rrf_ordered_dense.append(s)
        old_top1 = rrf_ordered_dense[0] if rrf_ordered_dense else None
        old_mean3 = (sum(rrf_ordered_dense[:3]) / 3.0) if len(rrf_ordered_dense) >= 3 else None

        # 3. Ground truth presence and metrics
        top5_ids = [c.chunk_id for c in fused_cands[:5]]
        top20_ids = [c.chunk_id for c in fused_cands[:20]]

        top5_hits = [cid for cid in top5_ids if cid in gt_chunks]
        top20_hits = [cid for cid in top20_ids if cid in gt_chunks]

        hit5 = 1.0 if len(top5_hits) > 0 else 0.0
        recall5 = len(top5_hits) / float(len(gt_chunks)) if gt_chunks else 0.0
        hit20 = 1.0 if len(top20_hits) > 0 else 0.0
        recall20 = len(top20_hits) / float(len(gt_chunks)) if gt_chunks else 0.0

        # Current evaluator decision (using old RRF-dependent scores)
        current_triggers_rewrite = not (
            old_top1 is not None and old_mean3 is not None
            and old_top1 >= 0.735 and old_mean3 >= 0.700
        )

        # 4. BM25 and overlap evidence
        # Overlap: chunks in fused_cands that have both dense_score and bm25_score
        overlap_chunks = [c for c in fused_cands if c.dense_score is not None and c.bm25_score is not None]
        top_bm25_score = max([c.bm25_score for c in fused_cands if c.bm25_score is not None], default=0.0)

        results.append({
            "qid": qid,
            "query": query,
            "gt_chunks": list(gt_chunks),
            "sorted_dense_top1": round(top1_dense, 4) if top1_dense else None,
            "sorted_dense_mean3": round(mean3_dense, 4) if mean3_dense else None,
            "sorted_dense_mean5": round(mean5_dense, 4) if mean5_dense else None,
            "old_rrf_dense_top1": round(old_top1, 4) if old_top1 else None,
            "old_rrf_dense_mean3": round(old_mean3, 4) if old_mean3 else None,
            "mismatch_diff": round(top1_dense - old_top1, 4) if (top1_dense and old_top1) else 0.0,
            "hit5": hit5,
            "recall5": round(recall5, 4),
            "hit20": hit20,
            "recall20": round(recall20, 4),
            "top5_hits": top5_hits,
            "top20_hits": top20_hits,
            "current_triggers_rewrite": current_triggers_rewrite,
            "overlap_count": len(overlap_chunks),
            "top_bm25_score": round(top_bm25_score, 2),
        })

    out_file = PROJECT_ROOT / "reports" / "retrieval_evaluation" / "calibration_data_36q.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nCalibration data saved to {out_file}")
    print(f"Total questions analyzed: {len(results)}")


if __name__ == "__main__":
    main()
