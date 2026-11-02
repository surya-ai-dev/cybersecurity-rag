"""Independent Evaluation Suite for Cybersecurity RAG Retrieval Pipeline.

Evaluates:
  Configuration A: Dense Retrieval Only (BGE-M3 @ Top 20)
  Configuration B: BM25 Lexical Retrieval Only (Okapi @ Top 20)
  Configuration C: Hybrid Retrieval using RRF Fusion (Dense + BM25 @ Top 20)
  Configuration D: Hybrid Retrieval + Cross-Encoder Reranking (ms-marco-MiniLM-L-6-v2)

Metrics Computed:
  - Recall@K, Precision@K, Hit Rate@K (for K in 1, 3, 5, 10, 20)
  - Mean Reciprocal Rank (MRR@5, MRR@20)
  - Normalized Discounted Cumulative Gain (NDCG@1, NDCG@3, NDCG@5, NDCG@10, NDCG@20)
  - Stage and End-to-End Latencies (ms)

Ground Truth Source:
  data/evaluation/retrieval_ground_truth_v2.json (36 questions)

Reports Generated:
  reports/retrieval_evaluation/retrieval_evaluation_<timestamp>.json
  reports/retrieval_evaluation/retrieval_evaluation_<timestamp>.md
"""

from __future__ import annotations

import argparse
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
from app.core.models import ChunkMetadata, RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import RRFFusion

# Evaluation Cutoffs
EVAL_K_VALUES: List[int] = [1, 3, 5, 10, 20]
DEFAULT_RETRIEVAL_TOP_K: int = 20
DEFAULT_RERANK_TOP_N: int = 20
PRODUCTION_CUTOFF_K: int = 5


# ============================================================================
# METRICS COMPUTATION (Pure Functional Implementation)
# ============================================================================

def compute_hit_rate(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int) -> float:
    """Compute Hit Rate@K: 1.0 if at least one relevant chunk is in top-k, else 0.0."""
    if not ground_truth or k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    return 1.0 if any(cid in ground_truth for cid in top_k) else 0.0


def compute_recall(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int) -> float:
    """Compute Recall@K: fraction of ground-truth chunks retrieved in top-k."""
    if not ground_truth or k <= 0:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    hits = len(top_k_set.intersection(ground_truth))
    return float(hits) / float(len(ground_truth))


def compute_precision(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int) -> float:
    """Compute Precision@K: fraction of retrieved top-k chunks that are relevant."""
    if k <= 0:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    hits = len(top_k_set.intersection(ground_truth))
    return float(hits) / float(k)


def compute_reciprocal_rank(retrieved_ids: Sequence[str], ground_truth: Set[str], k: Optional[int] = None) -> float:
    """Compute Reciprocal Rank: 1 / rank of first relevant chunk, or 0.0 if not found within k."""
    if not ground_truth:
        return 0.0
    candidates = retrieved_ids[:k] if k is not None else retrieved_ids
    for rank, cid in enumerate(candidates, start=1):
        if cid in ground_truth:
            return 1.0 / float(rank)
    return 0.0


def compute_ndcg(retrieved_ids: Sequence[str], ground_truth: Set[str], k: int) -> float:
    """Compute Normalized Discounted Cumulative Gain (NDCG@K) with binary relevance.

    Formula:
        DCG@k = sum_{i=1}^k (rel_i / log2(i + 1))
        IDCG@k = sum_{i=1}^{min(k, |G|)} (1.0 / log2(i + 1))
        NDCG@k = DCG@k / IDCG@k
    """
    if not ground_truth or k <= 0:
        return 0.0

    # DCG
    dcg = 0.0
    for rank, cid in enumerate(retrieved_ids[:k], start=1):
        if cid in ground_truth:
            dcg += 1.0 / math.log2(rank + 1)

    # IDCG (ideal placement of all available relevant items up to k)
    ideal_hits = min(k, len(ground_truth))
    if ideal_hits == 0:
        return 0.0

    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return float(dcg / idcg) if idcg > 0 else 0.0


def compute_metrics_bundle(
    retrieved_ids: Sequence[str],
    ground_truth: Set[str],
    k_values: Sequence[int] = EVAL_K_VALUES,
) -> Dict[str, float]:
    """Compute full metric bundle (Hit, Recall, Precision, MRR, NDCG) for candidate list."""
    bundle: Dict[str, float] = {}
    for k in k_values:
        bundle[f"hit@{k}"] = compute_hit_rate(retrieved_ids, ground_truth, k)
        bundle[f"recall@{k}"] = compute_recall(retrieved_ids, ground_truth, k)
        bundle[f"precision@{k}"] = compute_precision(retrieved_ids, ground_truth, k)
        bundle[f"ndcg@{k}"] = compute_ndcg(retrieved_ids, ground_truth, k)

    # Reciprocal ranks at key thresholds
    bundle["mrr@5"] = compute_reciprocal_rank(retrieved_ids, ground_truth, k=5)
    bundle["mrr@20"] = compute_reciprocal_rank(retrieved_ids, ground_truth, k=20)
    return bundle


# ============================================================================
# DATASET VALIDATION
# ============================================================================

def validate_evaluation_dataset(
    gt_path: Path,
    known_chunk_ids: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Validate ground-truth dataset structure and verify that all target chunks exist.

    Args:
        gt_path: Path to retrieval_ground_truth_v2.json.
        known_chunk_ids: Set of chunk IDs resolved in the loaded corpus / vector index.

    Returns:
        Validated dictionary of ground-truth questions.

    Raises:
        ValueError: If structure is malformed or required chunks are unresolvable.
        FileNotFoundError: If ground-truth file is missing.
    """
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground-truth dataset not found at: {gt_path}")

    with open(gt_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ground-truth file {gt_path} contains invalid JSON: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise ValueError(f"Ground-truth data in {gt_path} must be a non-empty dictionary.")

    required_keys = {"question_id", "question", "document_ids", "relevant_chunks"}
    missing_fields = []
    unresolvable_chunks: List[Tuple[str, str]] = []

    for qid, entry in data.items():
        if not isinstance(entry, dict):
            missing_fields.append(f"{qid}: entry is not a dictionary")
            continue

        missing = required_keys - set(entry.keys())
        if missing:
            missing_fields.append(f"{qid}: missing required fields {missing}")

        rel_chunks = entry.get("relevant_chunks")
        if not isinstance(rel_chunks, list) or len(rel_chunks) == 0:
            missing_fields.append(f"{qid}: relevant_chunks must be a non-empty list")
            continue

        if known_chunk_ids is not None:
            for cid in rel_chunks:
                if cid not in known_chunk_ids:
                    unresolvable_chunks.append((qid, str(cid)))

    if missing_fields:
        raise ValueError(
            f"Ground-truth dataset schema validation failed with {len(missing_fields)} errors:\n"
            + "\n".join(missing_fields[:10])
        )

    if unresolvable_chunks:
        sample_missing = unresolvable_chunks[:10]
        raise ValueError(
            f"Dataset validation failed: {len(unresolvable_chunks)} ground-truth chunk IDs cannot be resolved in the corpus:\n"
            + "\n".join(f"  {qid} -> {cid}" for qid, cid in sample_missing)
        )

    return data


# ============================================================================
# EVALUATION HARNESS
# ============================================================================

def extract_chunk_info(chunk: Any, rank: int, ground_truth: Set[str]) -> Dict[str, Any]:
    """Extract diagnostic information and score from a retrieved chunk object."""
    chunk_id = getattr(chunk, "chunk_id", None) or chunk.get("chunk_id", "Unknown")
    text = getattr(chunk, "text", None) or chunk.get("text", "")
    metadata = getattr(chunk, "metadata", None) or chunk.get("metadata", {})

    if isinstance(metadata, ChunkMetadata):
        doc_id = metadata.document_id
        section = metadata.section
    elif isinstance(metadata, dict):
        doc_id = metadata.get("document_id") or metadata.get("document") or "Unknown"
        section = metadata.get("section", "Unknown")
    else:
        doc_id = "Unknown"
        section = "Unknown"

    score_val: Optional[float] = None
    reranker_score = getattr(chunk, "reranker_score", None) if hasattr(chunk, "reranker_score") else chunk.get("reranker_score")
    rrf_score = getattr(chunk, "rrf_score", None) if hasattr(chunk, "rrf_score") else chunk.get("rrf_score")
    dense_score = getattr(chunk, "dense_score", None) if hasattr(chunk, "dense_score") else chunk.get("dense_score")
    bm25_score = getattr(chunk, "bm25_score", None) if hasattr(chunk, "bm25_score") else chunk.get("bm25_score")
    raw_score = getattr(chunk, "score", None) if hasattr(chunk, "score") else chunk.get("score")

    if reranker_score is not None:
        score_val = float(reranker_score)
        score_type = "reranker_score"
    elif rrf_score is not None:
        score_val = float(rrf_score)
        score_type = "rrf_score"
    elif dense_score is not None:
        score_val = float(dense_score)
        score_type = "dense_score"
    elif bm25_score is not None:
        score_val = float(bm25_score)
        score_type = "bm25_score"
    elif raw_score is not None:
        score_val = float(raw_score)
        score_type = "score"
    else:
        score_type = "none"

    return {
        "rank": rank,
        "chunk_id": str(chunk_id),
        "document_id": str(doc_id),
        "section": str(section),
        "score": score_val,
        "score_type": score_type,
        "is_relevant": str(chunk_id) in ground_truth,
        "text_preview": str(text)[:160].replace("\n", " ").strip() + "...",
    }


class RetrievalEvaluator:
    """Orchestrates multi-configuration benchmark of the retrieval pipeline."""

    def __init__(
        self,
        dense_retriever: Optional[DenseRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        rrf_fusion: Optional[RRFFusion] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        retrieval_top_k: int = DEFAULT_RETRIEVAL_TOP_K,
        rerank_top_n: int = DEFAULT_RERANK_TOP_N,
    ) -> None:
        self.dense_retriever = dense_retriever or DenseRetriever()
        self.bm25_retriever = bm25_retriever or BM25Retriever()
        self.rrf_fusion = rrf_fusion or RRFFusion(k=settings.rrf_k)
        self.reranker = reranker or CrossEncoderReranker(
            model_name=getattr(settings, "reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        )
        self.retrieval_top_k = retrieval_top_k
        self.rerank_top_n = rerank_top_n

        # Eagerly warm up model weights so loading time does not pollute query 1 latency
        if hasattr(self.dense_retriever, "_ensure_initialized"):
            self.dense_retriever._ensure_initialized()
        if hasattr(self.bm25_retriever, "_ensure_initialized"):
            self.bm25_retriever._ensure_initialized()
        if hasattr(self.reranker, "_ensure_initialized"):
            self.reranker._ensure_initialized()

    def evaluate_question(
        self,
        qid: str,
        question_text: str,
        expected_chunks: List[str],
        expected_docs: List[str],
    ) -> Dict[str, Any]:
        """Evaluate a single question across all four retrieval configurations."""
        gt_set = set(expected_chunks)
        question_result: Dict[str, Any] = {
            "question_id": qid,
            "question": question_text,
            "expected_chunks": expected_chunks,
            "expected_documents": expected_docs,
            "configurations": {},
            "errors": {},
        }

        # --------------------------------------------------------------------
        # Config A: Dense Retrieval (BGE-M3)
        # --------------------------------------------------------------------
        dense_candidates: List[RetrievedChunk] = []
        dense_latency = 0.0
        try:
            t0 = time.perf_counter()
            dense_candidates = self.dense_retriever.retrieve(
                question_text,
                top_k=self.retrieval_top_k,
            )
            dense_latency = (time.perf_counter() - t0) * 1000
            dense_cids = [c.chunk_id for c in dense_candidates]
            dense_info = [extract_chunk_info(c, idx, gt_set) for idx, c in enumerate(dense_candidates, start=1)]
            question_result["configurations"]["A_dense_only"] = {
                "name": "Dense Retrieval Only (BGE-M3)",
                "latency_ms": round(dense_latency, 2),
                "retrieved_count": len(dense_candidates),
                "metrics": compute_metrics_bundle(dense_cids, gt_set),
                "top_chunks": dense_info,
            }
        except Exception as exc:
            question_result["errors"]["A_dense_only"] = str(exc)

        # --------------------------------------------------------------------
        # Config B: BM25 Lexical Retrieval (Okapi)
        # --------------------------------------------------------------------
        bm25_candidates: List[RetrievedChunk] = []
        bm25_latency = 0.0
        try:
            t0 = time.perf_counter()
            bm25_candidates = self.bm25_retriever.retrieve(
                question_text,
                top_k=self.retrieval_top_k,
            )
            bm25_latency = (time.perf_counter() - t0) * 1000
            bm25_cids = [c.chunk_id for c in bm25_candidates]
            bm25_info = [extract_chunk_info(c, idx, gt_set) for idx, c in enumerate(bm25_candidates, start=1)]
            question_result["configurations"]["B_bm25_only"] = {
                "name": "BM25 Retrieval Only (Okapi)",
                "latency_ms": round(bm25_latency, 2),
                "retrieved_count": len(bm25_candidates),
                "metrics": compute_metrics_bundle(bm25_cids, gt_set),
                "top_chunks": bm25_info,
            }
        except Exception as exc:
            question_result["errors"]["B_bm25_only"] = str(exc)

        # --------------------------------------------------------------------
        # Config C: Hybrid Retrieval using RRF Fusion
        # --------------------------------------------------------------------
        hybrid_candidates: List[RetrievedChunk] = []
        hybrid_latency = 0.0
        try:
            t0 = time.perf_counter()
            hybrid_candidates = self.rrf_fusion.fuse(
                [dense_candidates, bm25_candidates],
                top_k=self.retrieval_top_k,
            )
            fusion_cost = (time.perf_counter() - t0) * 1000
            hybrid_latency = dense_latency + bm25_latency + fusion_cost
            hybrid_cids = [c.chunk_id for c in hybrid_candidates]
            hybrid_info = [extract_chunk_info(c, idx, gt_set) for idx, c in enumerate(hybrid_candidates, start=1)]
            question_result["configurations"]["C_hybrid_rrf"] = {
                "name": "Hybrid Retrieval (Dense + BM25 + RRF)",
                "latency_ms": round(hybrid_latency, 2),
                "fusion_latency_ms": round(fusion_cost, 2),
                "retrieved_count": len(hybrid_candidates),
                "metrics": compute_metrics_bundle(hybrid_cids, gt_set),
                "top_chunks": hybrid_info,
            }
        except Exception as exc:
            question_result["errors"]["C_hybrid_rrf"] = str(exc)

        # --------------------------------------------------------------------
        # Config D: Hybrid Retrieval + Cross-Encoder Reranking
        # --------------------------------------------------------------------
        try:
            t0 = time.perf_counter()
            reranked_candidates = self.reranker.rerank(
                question_text,
                hybrid_candidates,
                top_n=self.rerank_top_n,
            )
            rerank_cost = (time.perf_counter() - t0) * 1000
            total_latency = hybrid_latency + rerank_cost
            reranked_cids = [c.chunk_id for c in reranked_candidates]
            reranked_info = [extract_chunk_info(c, idx, gt_set) for idx, c in enumerate(reranked_candidates, start=1)]
            question_result["configurations"]["D_hybrid_reranked"] = {
                "name": "Hybrid + Cross-Encoder Reranker",
                "latency_ms": round(total_latency, 2),
                "reranker_latency_ms": round(rerank_cost, 2),
                "retrieved_count": len(reranked_candidates),
                "metrics": compute_metrics_bundle(reranked_cids, gt_set),
                "top_chunks": reranked_info,
            }
        except Exception as exc:
            question_result["errors"]["D_hybrid_reranked"] = str(exc)

        return question_result

    def run_benchmark(
        self,
        dataset: Dict[str, Dict[str, Any]],
        target_ids: Optional[Sequence[str]] = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """Execute full benchmark over the evaluation dataset."""
        question_keys = list(dataset.keys())
        if target_ids is not None:
            question_keys = [qid for qid in question_keys if qid in target_ids]

        if not question_keys:
            raise ValueError("No questions selected for benchmark.")

        print("=" * 80)
        print(f"STARTING RETRIEVAL BENCHMARK: {len(question_keys)} QUESTIONS")
        print("=" * 80)

        per_question_results: List[Dict[str, Any]] = []

        for index, qid in enumerate(question_keys, start=1):
            entry = dataset[qid]
            q_text = entry["question"]
            expected_chunks = entry["relevant_chunks"]
            expected_docs = entry.get("document_ids", [])

            if verbose:
                print(f"\n[{index}/{len(question_keys)}] Evaluating {qid}: {q_text[:75]}...")
                print(f"    Expected chunks ({len(expected_chunks)}): {expected_chunks}")

            q_res = self.evaluate_question(
                qid=qid,
                question_text=q_text,
                expected_chunks=expected_chunks,
                expected_docs=expected_docs,
            )
            per_question_results.append(q_res)

            if verbose:
                # Print quick snapshot of Hit@5 across configs
                status_parts = []
                for cfg_key in ["A_dense_only", "B_bm25_only", "C_hybrid_rrf", "D_hybrid_reranked"]:
                    cfg_data = q_res["configurations"].get(cfg_key)
                    if cfg_data:
                        hit5 = int(cfg_data["metrics"].get("hit@5", 0.0))
                        status_parts.append(f"{cfg_key[:1]}:{hit5}")
                    else:
                        status_parts.append(f"{cfg_key[:1]}:ERR")
                print(f"    Hit@5 Snapshot -> {' | '.join(status_parts)}")

        # Compute Macro-Aggregated Metrics
        aggregate_summary = self._compute_aggregates(per_question_results)

        return {
            "benchmark_metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_questions": len(question_keys),
                "evaluated_question_ids": question_keys,
                "retrieval_top_k": self.retrieval_top_k,
                "rerank_top_n": self.rerank_top_n,
                "reranker_model": self.reranker.model_name,
                "embedding_model": self.dense_retriever.embedding_model_name,
                "production_cutoff_k": PRODUCTION_CUTOFF_K,
            },
            "aggregate_metrics": aggregate_summary,
            "per_question_results": per_question_results,
        }

    def _compute_aggregates(self, per_question_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute macro-averaged metrics and latency statistics across all questions."""
        config_keys = ["A_dense_only", "B_bm25_only", "C_hybrid_rrf", "D_hybrid_reranked"]
        aggregates: Dict[str, Any] = {}

        for cfg_key in config_keys:
            latencies: List[float] = []
            metrics_accum: Dict[str, List[float]] = {}

            for q_res in per_question_results:
                cfg_data = q_res["configurations"].get(cfg_key)
                if not cfg_data:
                    continue
                latencies.append(cfg_data["latency_ms"])
                for m_name, m_val in cfg_data["metrics"].items():
                    if m_name not in metrics_accum:
                        metrics_accum[m_name] = []
                    metrics_accum[m_name].append(m_val)

            n_samples = len(latencies)
            if n_samples == 0:
                continue

            cfg_name = per_question_results[0]["configurations"][cfg_key]["name"]
            mean_metrics = {m: round(sum(vals) / float(len(vals)), 4) for m, vals in metrics_accum.items()}

            latencies.sort()
            median_latency = latencies[n_samples // 2]
            p95_latency = latencies[min(int(n_samples * 0.95), n_samples - 1)]
            avg_latency = round(sum(latencies) / float(n_samples), 2)

            aggregates[cfg_key] = {
                "name": cfg_name,
                "evaluated_queries": n_samples,
                "latency_ms": {
                    "mean": avg_latency,
                    "median": round(median_latency, 2),
                    "p95": round(p95_latency, 2),
                },
                "metrics": mean_metrics,
            }

        return aggregates


# ============================================================================
# REPORT GENERATORS (JSON & MARKDOWN)
# ============================================================================

def format_markdown_report(benchmark_data: Dict[str, Any]) -> str:
    """Format full benchmark run into an executive-ready Markdown report."""
    meta = benchmark_data["benchmark_metadata"]
    aggr = benchmark_data["aggregate_metrics"]
    per_q = benchmark_data["per_question_results"]

    lines: List[str] = [
        "# Cybersecurity RAG: Retrieval Pipeline Benchmark Report",
        "",
        f"- **Timestamp:** `{meta['timestamp']}`",
        f"- **Questions Evaluated:** `{meta['total_questions']}`",
        f"- **Dense Embedding Model:** `{meta['embedding_model']}`",
        f"- **Cross-Encoder Reranker:** `{meta['reranker_model']}`",
        f"- **Initial Candidate Top-K:** `{meta['retrieval_top_k']}`",
        f"- **Production Cutoff:** `Top {meta['production_cutoff_k']}`",
        "",
        "---",
        "",
        "## 1. Executive Summary & Configuration Comparison",
        "",
        "| Configuration | Hit@1 | Hit@5 | Hit@20 | Recall@5 | Recall@20 | Precision@5 | MRR@20 | NDCG@5 | NDCG@20 | Avg Latency |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for cfg_key in ["A_dense_only", "B_bm25_only", "C_hybrid_rrf", "D_hybrid_reranked"]:
        cfg = aggr.get(cfg_key)
        if not cfg:
            continue
        m = cfg["metrics"]
        lat = cfg["latency_ms"]["mean"]
        name = cfg["name"]
        lines.append(
            f"| **{name}** | {m.get('hit@1', 0.0):.2%} | **{m.get('hit@5', 0.0):.2%}** | {m.get('hit@20', 0.0):.2%} | "
            f"**{m.get('recall@5', 0.0):.2%}** | {m.get('recall@20', 0.0):.2%} | {m.get('precision@5', 0.0):.2%} | "
            f"**{m.get('mrr@20', 0.0):.4f}** | **{m.get('ndcg@5', 0.0):.4f}** | {m.get('ndcg@20', 0.0):.4f} | {lat:.1f} ms |"
        )

    lines.extend([
        "",
        "> [!NOTE]",
        "> **Production Impact:** Configuration D evaluates the actual candidate stream delivered into the context builder. "
        "Top-5 metrics represent the exact context injected into prompt generation, while Top-20 metrics reflect the underlying candidate pool ceiling.",
        "",
        "---",
        "",
        "## 2. Per-Question Detailed Performance Matrix",
        "",
        "| QID | Question Preview | Expected Chunks | Dense Hit@5 | BM25 Hit@5 | Hybrid Hit@5 | Reranked Hit@5 | Reranked Recall@5 | Reranked MRR@20 |",
        "|---|---|---|---|---|---|---|---|---|",
    ])

    for q in per_q:
        qid = q["question_id"]
        q_text = q["question"][:45].replace("|", "\\|") + ("..." if len(q["question"]) > 45 else "")
        n_exp = len(q["expected_chunks"])

        cfgs = q["configurations"]
        d_hit = int(cfgs.get("A_dense_only", {}).get("metrics", {}).get("hit@5", 0.0))
        b_hit = int(cfgs.get("B_bm25_only", {}).get("metrics", {}).get("hit@5", 0.0))
        h_hit = int(cfgs.get("C_hybrid_rrf", {}).get("metrics", {}).get("hit@5", 0.0))

        d_cfg = cfgs.get("D_hybrid_reranked", {})
        r_hit = int(d_cfg.get("metrics", {}).get("hit@5", 0.0))
        r_rec = d_cfg.get("metrics", {}).get("recall@5", 0.0)
        r_mrr = d_cfg.get("metrics", {}).get("mrr@20", 0.0)

        d_str = "✅" if d_hit else "❌"
        b_str = "✅" if b_hit else "❌"
        h_str = "✅" if h_hit else "❌"
        r_str = "✅" if r_hit else "❌"

        lines.append(
            f"| **{qid}** | {q_text} | {n_exp} | {d_str} | {b_str} | {h_str} | {r_str} | {r_rec:.1%} | {r_mrr:.3f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Top Missing or Suboptimal Queries (Config D Hit@5 = 0)",
        "",
    ])

    suboptimal = [
        q for q in per_q
        if q["configurations"].get("D_hybrid_reranked", {}).get("metrics", {}).get("hit@5", 0.0) < 1.0
    ]

    if not suboptimal:
        lines.append(f"🎉 **Zero misses! All {meta['total_questions']} evaluated questions achieved 100% Hit@5 in the reranked pipeline.**")
    else:
        for q in suboptimal:
            qid = q["question_id"]
            cfg_d = q["configurations"].get("D_hybrid_reranked", {})
            m = cfg_d.get("metrics", {})
            lines.append(f"### Question {qid}")
            lines.append(f"- **Query:** {q['question']}")
            lines.append(f"- **Expected Chunks:** `{q['expected_chunks']}`")
            lines.append(f"- **Hit@5:** `{m.get('hit@5', 0.0)}` | **Hit@20:** `{m.get('hit@20', 0.0)}` | **MRR@20:** `{m.get('mrr@20', 0.0)}`")
            top_chunks = cfg_d.get("top_chunks", [])[:5]
            lines.append("- **Top-5 Retrieved Chunks:**")
            for c in top_chunks:
                rel_mark = "🎯 [RELEVANT]" if c["is_relevant"] else "⚪"
                score_str = f"score: {c['score']:.4f}" if c['score'] is not None else "no score"
                lines.append(f"  {c['rank']}. {rel_mark} `{c['chunk_id']}` ({c['document_id']}) — {score_str}")
            lines.append("")

    return "\n".join(lines)


def save_reports(
    benchmark_data: Dict[str, Any],
    reports_dir: Path,
) -> Tuple[Path, Path]:
    """Persist JSON and Markdown benchmark reports with unique timestamps."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = reports_dir / f"retrieval_evaluation_{ts}.json"
    md_path = reports_dir / f"retrieval_evaluation_{ts}.md"

    # Write unique timestamped artifacts
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)

    md_content = format_markdown_report(benchmark_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Also update 'latest' pointers for convenience
    latest_json = reports_dir / "latest_retrieval_evaluation.json"
    latest_md = reports_dir / "latest_retrieval_evaluation.md"
    with open(latest_json, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)
    with open(latest_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    return json_path, md_path


# ============================================================================
# CLI & SMOKE TEST ENTRY POINT
# ============================================================================

def main() -> None:
    """CLI orchestrator for retrieval evaluation."""
    parser = argparse.ArgumentParser(description="Evaluate Cybersecurity RAG Retrieval Pipeline")
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=str(PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_v2.json"),
        help="Path to ground-truth JSON dataset (v2).",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run limited smoke test on first question (Q1) to verify all components and pipelines.",
    )
    parser.add_argument(
        "--questions",
        nargs="+",
        default=None,
        help="Optional list of specific question IDs to benchmark (e.g. Q1 Q3 Q14).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_RETRIEVAL_TOP_K,
        help="Number of candidates retrieved from dense and BM25 retrievers.",
    )
    parser.add_argument(
        "--rerank-top-n",
        type=int,
        default=DEFAULT_RERANK_TOP_N,
        help="Number of candidate chunks evaluated by cross-encoder reranker.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "reports" / "retrieval_evaluation"),
        help="Directory where evaluation artifacts will be written.",
    )

    args = parser.parse_args()
    gt_path = Path(args.ground_truth)
    output_dir = Path(args.output_dir)

    print("\n" + "=" * 80)
    print("CYBERSECURITY RAG: RETRIEVAL PIPELINE EVALUATION ENGINE")
    print("=" * 80)
    print(f"Ground Truth Dataset: {gt_path}")
    print(f"Output Directory:     {output_dir}")
    print(f"Smoke Test Mode:      {args.smoke_test}")

    # 1. Initialize retrievers
    print("\n[Step 1/4] Initializing retrievers and loading models...")
    t_init = time.perf_counter()
    dense_retriever = DenseRetriever()
    bm25_retriever = BM25Retriever()
    rrf_fusion = RRFFusion(k=settings.rrf_k)
    reranker = CrossEncoderReranker()

    # Preload to resolve known chunk IDs for validation
    bm25_docs = bm25_retriever.documents
    known_chunk_ids = {doc["chunk_id"] for doc in bm25_docs}
    print(f"Loaded {len(known_chunk_ids)} unique chunk IDs from corpus.")
    print(f"Initialization completed in {(time.perf_counter() - t_init):.2f}s")

    # 2. Validate Ground-Truth Dataset
    print("\n[Step 2/4] Validating ground-truth dataset integrity...")
    dataset = validate_evaluation_dataset(gt_path, known_chunk_ids=known_chunk_ids)
    print(f"Validation SUCCESS: {len(dataset)} verified questions loaded.")

    # 3. Determine questions to run
    target_ids = args.questions
    if args.smoke_test:
        first_qid = list(dataset.keys())[0]
        target_ids = [first_qid]
        print(f"\n[Smoke Test] Restricted execution to single query: {target_ids}")

    # 4. Execute Benchmark
    print("\n[Step 3/4] Running multi-configuration benchmark...")
    evaluator = RetrievalEvaluator(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
        rrf_fusion=rrf_fusion,
        reranker=reranker,
        retrieval_top_k=args.top_k,
        rerank_top_n=args.rerank_top_n,
    )

    benchmark_data = evaluator.run_benchmark(
        dataset=dataset,
        target_ids=target_ids,
        verbose=True,
    )

    # 5. Persist Reports
    print("\n[Step 4/4] Writing benchmark artifacts...")
    json_path, md_path = save_reports(benchmark_data, output_dir)
    print(f"Saved JSON report:     {json_path}")
    print(f"Saved Markdown report: {md_path}")

    # Print summary table to console
    print("\n" + "=" * 90)
    print("BENCHMARK AGGREGATE RESULTS SUMMARY")
    print("=" * 90)
    print(f"{'Configuration':<34} | {'Hit@1':<7} | {'Hit@5':<7} | {'Recall@5':<9} | {'MRR@20':<8} | {'NDCG@5':<8} | {'Latency':<10}")
    print("-" * 90)
    for cfg_key in ["A_dense_only", "B_bm25_only", "C_hybrid_rrf", "D_hybrid_reranked"]:
        cfg = benchmark_data["aggregate_metrics"].get(cfg_key)
        if not cfg:
            continue
        m = cfg["metrics"]
        lat = cfg["latency_ms"]["mean"]
        name = cfg["name"]
        print(
            f"{name:<34} | {m.get('hit@1', 0.0):<7.2%} | {m.get('hit@5', 0.0):<7.2%} | "
            f"{m.get('recall@5', 0.0):<9.2%} | {m.get('mrr@20', 0.0):<8.4f} | {m.get('ndcg@5', 0.0):<8.4f} | {lat:.1f} ms"
        )
    print("=" * 90)
    print("Evaluation run completed successfully.\n")


if __name__ == "__main__":
    main()
