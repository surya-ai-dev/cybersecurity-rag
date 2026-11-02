"""Controlled 36-Question Retrieval Benchmark: Baseline vs Revised Experimental Rewriter.

Evaluates all 36 questions in data/evaluation/retrieval_ground_truth_v2.json:
  1. Baseline: Original question text through the full retrieval pipeline
     (Dense 20 + BM25 20 -> RRF 20 -> Cross-Encoder -> Top 5).
  2. Revised Experimental Rewriter: LLM-generated search query (qwen/qwen3.8-27b with
     domain-focused technical expansion prompt) through the exact same retrieval pipeline.

Reports Generated:
  reports/retrieval_evaluation/experiment_36q_revised_rewriter.json
  reports/retrieval_evaluation/experiment_36q_revised_rewriter.md
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

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from groq import Groq

from app.core.config import settings
from app.core.models import ChunkMetadata, RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import RRFFusion

# Revised System Prompt for Experimental Query Rewriter
REVISED_QUERY_REWRITE_SYSTEM_PROMPT = """You are an expert cybersecurity document search query optimizer.
Your task is to rewrite the user's question into an optimal search query for retrieving technical sections from authoritative cybersecurity publications (such as NIST Special Publications, ISO/IEC, and OWASP).

CRITICAL RULES:
1. Output ONLY the search query on a single line. Do not include quotes, explanations, preambles, or markdown formatting.
2. DO NOT answer the question.
3. PRESERVE all document standards, publication numbers, control IDs, and formal designations exactly (e.g., "NIST SP 800-145", "NIST SP 800-218", "SP 800-53", "SSDF") present in the user question.
4. DO NOT hallucinate, inject, or guess document numbers or publication IDs unless the user question explicitly mentions them.
5. AVOID generic abstract filler terms (e.g., do NOT append broad textbook terms like "confidentiality, integrity, availability" or "security risks") that dilute search specificity.
6. EXPAND specific technical mechanisms, architectural concepts, and domain terms directly pertinent to the question's core subject:
   - For cloud data storage and data protection: data protection, shared environment, multi-tenant isolation, data co-location, database isolation, data at rest, encryption, cryptographic key management.
   - For cloud security monitoring: event logs, provider audit controls, incident response, forensics limitations.
   - For incident handling: preparation, detection and analysis, containment eradication recovery, post-incident activity.
   - For SSDF practice groups: Prepare the Organization PO, Protect Software PS, Produce Well-Secured Software PW, Respond to Vulnerabilities RV.
   - For cloud computing characteristics: on-demand self-service, broad network access, resource pooling, rapid elasticity, measured service.
   - For zero trust architectures: policy enforcement point PEP, policy decision point PDP, continuous verification, mutual TLS.
7. Return a clean, concise, keyword-rich technical search query.
"""

RETRIEVAL_TOP_K = 20
RRF_POOL_TOP_K = 20
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


def compute_all_metrics(retrieved_ids: Sequence[str], ground_truth: Set[str]) -> Dict[str, float]:
    """Compute metrics bundle at K=1, 5, 20."""
    return {
        "hit@1": compute_hit_rate(retrieved_ids, ground_truth, k=1),
        "hit@5": compute_hit_rate(retrieved_ids, ground_truth, k=5),
        "hit@20": compute_hit_rate(retrieved_ids, ground_truth, k=20),
        "recall@1": compute_recall(retrieved_ids, ground_truth, k=1),
        "recall@5": compute_recall(retrieved_ids, ground_truth, k=5),
        "recall@20": compute_recall(retrieved_ids, ground_truth, k=20),
        "precision@5": compute_precision(retrieved_ids, ground_truth, k=5),
        "mrr@5": compute_mrr(retrieved_ids, ground_truth, k=5),
        "mrr@20": compute_mrr(retrieved_ids, ground_truth, k=20),
        "ndcg@5": compute_ndcg(retrieved_ids, ground_truth, k=5),
        "ndcg@20": compute_ndcg(retrieved_ids, ground_truth, k=20),
    }


# ============================================================================
# EXPERIMENTAL REWRITER IMPLEMENTATION
# ============================================================================

class ExperimentalQueryRewriter:
    """Isolated query rewriter using the revised prompt with qwen/qwen3.8-27b."""

    def __init__(self, api_key: str, model_name: str = "qwen/qwen3.8-27b") -> None:
        self.client = Groq(api_key=api_key)
        self.model_name = model_name

    def rewrite(self, question: str) -> Tuple[str, float]:
        """Generate rewritten search query using the revised experimental prompt."""
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": REVISED_QUERY_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": f"User question: {question.strip()}\nSearch query:"},
            ],
            temperature=0.0,
            max_completion_tokens=256,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        raw_text = resp.choices[0].message.content or ""

        # Clean quotes and prefixes
        cleaned = raw_text.strip()
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()
        prefix_pattern = r"^(?:search\s+query|rewritten\s+query|query|optimized\s+query)\s*:\s*"
        cleaned = re.sub(prefix_pattern, "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = " ".join(cleaned.split())

        return cleaned if cleaned else question, latency_ms


# ============================================================================
# PIPELINE EXECUTION FOR A SINGLE QUERY
# ============================================================================

def execute_retrieval_pipeline(
    search_query: str,
    ground_truth: Set[str],
    dense_retriever: DenseRetriever,
    bm25_retriever: BM25Retriever,
    rrf_fusion: RRFFusion,
    reranker: CrossEncoderReranker,
) -> Tuple[List[Dict[str, Any]], Dict[str, float], float]:
    """Execute Dense 20 + BM25 20 -> RRF 20 -> Cross-Encoder 20 -> Top 5."""
    t0 = time.perf_counter()

    # 1. Retrieve candidates
    dense_candidates = dense_retriever.retrieve(search_query, top_k=RETRIEVAL_TOP_K)
    bm25_candidates = bm25_retriever.retrieve(search_query, top_k=RETRIEVAL_TOP_K)

    # 2. Fuse candidates
    hybrid_candidates = rrf_fusion.fuse([dense_candidates, bm25_candidates], top_k=RRF_POOL_TOP_K)

    # 3. Rerank candidates
    reranked_candidates = reranker.rerank(search_query, hybrid_candidates, top_n=RRF_POOL_TOP_K)
    pipeline_latency_ms = (time.perf_counter() - t0) * 1000

    # 4. Format top 5 and compute metrics
    top_5_chunks = reranked_candidates[:FINAL_TOP_K]
    top_5_ids = [c.chunk_id for c in top_5_chunks]

    metrics = compute_all_metrics(top_5_ids, ground_truth)

    final_summary = []
    for rank, c in enumerate(top_5_chunks, start=1):
        meta = getattr(c, "metadata", {})
        sec = meta.section if hasattr(meta, "section") else meta.get("section", "Unknown")
        doc = meta.document_id if hasattr(meta, "document_id") else meta.get("document_id", "Unknown")
        final_summary.append({
            "rank": rank,
            "chunk_id": c.chunk_id,
            "document_id": doc,
            "section": sec,
            "score": round(float(c.reranker_score), 4) if c.reranker_score is not None else None,
            "is_relevant": c.chunk_id in ground_truth,
        })

    return final_summary, metrics, pipeline_latency_ms


# ============================================================================
# MAIN BENCHMARK RUNNER
# ============================================================================

def main():
    print("=" * 80)
    print("CONTROLLED 36-QUESTION RETRIEVAL BENCHMARK: BASELINE vs REVISED REWRITER")
    print("=" * 80)

    # 1. Load ground truth
    gt_path = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_v2.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    question_keys = list(ground_truth.keys())
    print(f"Loaded {len(question_keys)} verified evaluation questions.")

    # 2. Initialize models
    print("\n[Step 1/3] Initializing and warming up models...")
    t_start = time.perf_counter()
    dense_retriever = DenseRetriever()
    bm25_retriever = BM25Retriever()
    rrf_fusion = RRFFusion(k=settings.rrf_k)
    reranker = CrossEncoderReranker()

    dense_retriever._ensure_initialized()
    bm25_retriever._ensure_initialized()
    reranker._ensure_initialized()
    print(f"Models initialized in {(time.perf_counter() - t_start):.2f}s")

    # 3. Initialize experimental rewriter
    api_key = getattr(settings, "groq_api_key", None) or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("ERROR: GROQ_API_KEY missing. Cannot run LLM rewriter.")
        sys.exit(1)

    rewriter = ExperimentalQueryRewriter(api_key=api_key)

    # 4. Iterate through all 36 questions
    print("\n[Step 2/3] Executing benchmark across all 36 questions...")
    results_list: List[Dict[str, Any]] = []

    for index, qid in enumerate(question_keys, start=1):
        q_data = ground_truth[qid]
        original_q = q_data["question"]
        expected_chunks = q_data["relevant_chunks"]
        gt_set = set(expected_chunks)

        print(f"\n[{index}/{len(question_keys)}] Evaluating {qid}...")
        print(f"  Original: \"{original_q[:70]}...\"")

        # Baseline execution
        base_top5, base_metrics, base_lat = execute_retrieval_pipeline(
            search_query=original_q,
            ground_truth=gt_set,
            dense_retriever=dense_retriever,
            bm25_retriever=bm25_retriever,
            rrf_fusion=rrf_fusion,
            reranker=reranker,
        )

        # Revised experimental rewriter execution
        rewritten_q, rewrite_lat = rewriter.rewrite(original_q)
        print(f"  Rewrite:  \"{rewritten_q[:70]}...\" ({rewrite_lat:.1f}ms)")

        rev_top5, rev_metrics, rev_ret_lat = execute_retrieval_pipeline(
            search_query=rewritten_q,
            ground_truth=gt_set,
            dense_retriever=dense_retriever,
            bm25_retriever=bm25_retriever,
            rrf_fusion=rrf_fusion,
            reranker=reranker,
        )

        # Comparison delta
        hit5_delta = rev_metrics["hit@5"] - base_metrics["hit@5"]
        recall5_delta = rev_metrics["recall@5"] - base_metrics["recall@5"]
        mrr5_delta = rev_metrics["mrr@5"] - base_metrics["mrr@5"]
        ndcg5_delta = rev_metrics["ndcg@5"] - base_metrics["ndcg@5"]

        if hit5_delta > 0 or (hit5_delta == 0 and recall5_delta > 0):
            status = "IMPROVED"
            status_symbol = "++"
        elif hit5_delta < 0 or (hit5_delta == 0 and recall5_delta < 0):
            status = "REGRESSED"
            status_symbol = "--"
        else:
            status = "NEUTRAL"
            status_symbol = "=="

        print(f"  Status: [{status_symbol}] Base Hit@5: {base_metrics['hit@5']:.0%} -> Rev Hit@5: {rev_metrics['hit@5']:.0%} | Recall: {base_metrics['recall@5']:.1%} -> {rev_metrics['recall@5']:.1%}")

        results_list.append({
            "question_id": qid,
            "original_question": original_q,
            "rewritten_question": rewritten_q,
            "expected_chunks": expected_chunks,
            "status": status,
            "baseline": {
                "metrics": base_metrics,
                "latency_ms": round(base_lat, 2),
                "top_5": base_top5,
            },
            "revised_rewriter": {
                "metrics": rev_metrics,
                "rewriter_latency_ms": round(rewrite_lat, 2),
                "pipeline_latency_ms": round(rev_ret_lat, 2),
                "total_latency_ms": round(rewrite_lat + rev_ret_lat, 2),
                "top_5": rev_top5,
            },
            "deltas": {
                "hit@5": hit5_delta,
                "recall@5": recall5_delta,
                "mrr@5": mrr5_delta,
                "ndcg@5": ndcg5_delta,
            },
        })

    # 5. Compute Aggregate Summary
    print("\n[Step 3/3] Calculating aggregate metrics and generating report...")

    num_q = len(results_list)
    improved_count = sum(1 for r in results_list if r["status"] == "IMPROVED")
    neutral_count = sum(1 for r in results_list if r["status"] == "NEUTRAL")
    regressed_count = sum(1 for r in results_list if r["status"] == "REGRESSED")

    def calc_mean(metric_name: str, group_key: str) -> float:
        return sum(r[group_key]["metrics"][metric_name] for r in results_list) / float(num_q)

    def calc_mean_lat(lat_key: str, group_key: str) -> float:
        if group_key == "baseline":
            return sum(r["baseline"]["latency_ms"] for r in results_list) / float(num_q)
        return sum(r["revised_rewriter"][lat_key] for r in results_list) / float(num_q)

    aggregate_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "total_questions": num_q,
            "improved_count": improved_count,
            "neutral_count": neutral_count,
            "regressed_count": regressed_count,
            "settings": {
                "retrieval_top_k": RETRIEVAL_TOP_K,
                "rrf_pool_top_k": RRF_POOL_TOP_K,
                "final_top_k": FINAL_TOP_K,
                "reranker_model": reranker.model_name,
                "embedding_model": dense_retriever.embedding_model_name,
                "rewriter_model": rewriter.model_name,
            },
        },
        "aggregate_metrics": {
            "baseline": {
                "hit@1": round(calc_mean("hit@1", "baseline"), 4),
                "hit@5": round(calc_mean("hit@5", "baseline"), 4),
                "hit@20": round(calc_mean("hit@20", "baseline"), 4),
                "recall@5": round(calc_mean("recall@5", "baseline"), 4),
                "recall@20": round(calc_mean("recall@20", "baseline"), 4),
                "precision@5": round(calc_mean("precision@5", "baseline"), 4),
                "mrr@5": round(calc_mean("mrr@5", "baseline"), 4),
                "mrr@20": round(calc_mean("mrr@20", "baseline"), 4),
                "ndcg@5": round(calc_mean("ndcg@5", "baseline"), 4),
                "ndcg@20": round(calc_mean("ndcg@20", "baseline"), 4),
                "avg_latency_ms": round(calc_mean_lat("latency_ms", "baseline"), 2),
            },
            "revised_rewriter": {
                "hit@1": round(calc_mean("hit@1", "revised_rewriter"), 4),
                "hit@5": round(calc_mean("hit@5", "revised_rewriter"), 4),
                "hit@20": round(calc_mean("hit@20", "revised_rewriter"), 4),
                "recall@5": round(calc_mean("recall@5", "revised_rewriter"), 4),
                "recall@20": round(calc_mean("recall@20", "revised_rewriter"), 4),
                "precision@5": round(calc_mean("precision@5", "revised_rewriter"), 4),
                "mrr@5": round(calc_mean("mrr@5", "revised_rewriter"), 4),
                "mrr@20": round(calc_mean("mrr@20", "revised_rewriter"), 4),
                "ndcg@5": round(calc_mean("ndcg@5", "revised_rewriter"), 4),
                "ndcg@20": round(calc_mean("ndcg@20", "revised_rewriter"), 4),
                "avg_rewriter_latency_ms": round(calc_mean_lat("rewriter_latency_ms", "revised_rewriter"), 2),
                "avg_pipeline_latency_ms": round(calc_mean_lat("pipeline_latency_ms", "revised_rewriter"), 2),
                "avg_total_latency_ms": round(calc_mean_lat("total_latency_ms", "revised_rewriter"), 2),
            },
        },
        "per_question_results": results_list,
    }

    # Save JSON and Markdown
    out_dir = PROJECT_ROOT / "reports" / "retrieval_evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "experiment_36q_revised_rewriter.json"
    md_path = out_dir / "experiment_36q_revised_rewriter.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(aggregate_data, f, indent=2)

    # Markdown report formatting
    lines = [
        "# 36-Question Retrieval Benchmark: Baseline vs Revised Experimental Rewriter",
        "",
        "- **Timestamp:** `" + aggregate_data["metadata"]["timestamp"] + "`",
        "- **Total Questions Evaluated:** `36`",
        f"- **Outcome Distribution:** Improved: `{improved_count}` | Neutral: `{neutral_count}` | Regressed: `{regressed_count}`",
        f"- **Dense Embedding Model:** `{dense_retriever.embedding_model_name}`",
        f"- **Cross-Encoder Model:** `{reranker.model_name}`",
        f"- **Rewriter Model:** `{rewriter.model_name}`",
        "- **Retrieval Pipeline Cutoffs:** `Dense=20, BM25=20, RRF Pool=20, Top Context=5`",
        "",
        "---",
        "",
        "## 1. Executive Macro-Average Comparison",
        "",
        "| Metric | Baseline (Original Queries) | Revised Rewriter (LLM Expanded) | Delta |",
        "|---|---|---|---|",
    ]

    base_ag = aggregate_data["aggregate_metrics"]["baseline"]
    rev_ag = aggregate_data["aggregate_metrics"]["revised_rewriter"]

    metric_keys = [
        ("Hit@1", "hit@1", "{:.2%}"),
        ("Hit@5 (Context Delivered)", "hit@5", "{:.2%}"),
        ("Hit@20 (Pool Ceiling)", "hit@20", "{:.2%}"),
        ("Recall@5", "recall@5", "{:.2%}"),
        ("Recall@20", "recall@20", "{:.2%}"),
        ("Precision@5", "precision@5", "{:.2%}"),
        ("MRR@5", "mrr@5", "{:.4f}"),
        ("MRR@20", "mrr@20", "{:.4f}"),
        ("NDCG@5", "ndcg@5", "{:.4f}"),
        ("NDCG@20", "ndcg@20", "{:.4f}"),
        ("Avg End-to-End Latency", "avg_latency_ms", "{:.1f} ms"),
    ]

    for label, m_key, fmt in metric_keys:
        if m_key == "avg_latency_ms":
            b_val = base_ag["avg_latency_ms"]
            r_val = rev_ag["avg_total_latency_ms"]
            delta = r_val - b_val
            lines.append(f"| **{label}** | {fmt.format(b_val)} | {fmt.format(r_val)} | +{delta:.1f} ms |")
        else:
            b_val = base_ag[m_key]
            r_val = rev_ag[m_key]
            delta = r_val - b_val
            delta_str = f"+{fmt.format(delta)}" if delta >= 0 else f"{fmt.format(delta)}"
            lines.append(f"| **{label}** | {fmt.format(b_val)} | {fmt.format(r_val)} | **{delta_str}** |")

    lines.extend([
        "",
        "---",
        "",
        "## 2. Per-Question Detailed Results Matrix",
        "",
        "| QID | Status | Base Hit@5 | Rev Hit@5 | Base Recall@5 | Rev Recall@5 | Base MRR@5 | Rev MRR@5 | Rewritten Query Preview |",
        "|---|---|---|---|---|---|---|---|---|",
    ])

    for r in results_list:
        qid = r["question_id"]
        st = r["status"]
        st_mark = "✅ IMPROVED" if st == "IMPROVED" else ("❌ REGRESSED" if st == "REGRESSED" else "⚪ NEUTRAL")
        bm = r["baseline"]["metrics"]
        rm = r["revised_rewriter"]["metrics"]
        rw_preview = r["rewritten_question"][:45].replace("|", "\\|") + ("..." if len(r["rewritten_question"]) > 45 else "")
        lines.append(
            f"| **{qid}** | {st_mark} | {bm['hit@5']:.0%} | **{rm['hit@5']:.0%}** | {bm['recall@5']:.1%} | **{rm['recall@5']:.1%}** | {bm['mrr@5']:.3f} | {rm['mrr@5']:.3f} | *{rw_preview}* |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Regressions Analysis (If Any)",
        "",
    ])

    regressions = [r for r in results_list if r["status"] == "REGRESSED"]
    if not regressions:
        lines.append("🎉 **Zero regressions! No question performed worse under the revised query rewriter.**")
    else:
        for reg in regressions:
            lines.append(f"### Question {reg['question_id']}")
            lines.append(f"- **Original Question:** *\"{reg['original_question']}\"*")
            lines.append(f"- **Rewritten Query:** *\"{reg['rewritten_question']}\"*")
            lines.append(f"- **Hit@5 Change:** `{reg['baseline']['metrics']['hit@5']:.0%}` -> `{reg['revised_rewriter']['metrics']['hit@5']:.0%}`")
            lines.append(f"- **Recall@5 Change:** `{reg['baseline']['metrics']['recall@5']:.1%}` -> `{reg['revised_rewriter']['metrics']['recall@5']:.1%}`")
            lines.append(f"- **Expected Chunks:** `{reg['expected_chunks']}`")
            lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nSaved full benchmark JSON report: {json_path}")
    print(f"Saved full benchmark Markdown report: {md_path}")
    print("\nBenchmark completed successfully.")


if __name__ == "__main__":
    main()
