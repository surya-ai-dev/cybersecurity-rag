"""Evaluation script for Q10, Q13, and Q19 on the unified Cybersecurity RAG pipeline.

Evaluates:
1. Dense Retrieval (BGE-M3)
2. BM25 Retrieval (Okapi)
3. Hybrid Retrieval (RRF Fusion)
4. Hybrid Retrieval + Adaptive Query Rewriter
5. Hybrid Retrieval + Cross-Encoder Reranker (BAAI/bge-reranker-v2-m3)
"""

import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.retrieval.dense import DenseRetriever
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.rrf import RRFFusion
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.confidence import ConfidenceEvaluator, merge_candidate_pools
from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.reranker import CrossEncoderReranker

TARGET_QUESTIONS = ["Q10", "Q13", "Q19"]
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def load_evaluation_data():
    gt_path = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_current.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    q_path = PROJECT_ROOT / "data" / "evaluation" / "evaluation_questions.json"
    with open(q_path, "r", encoding="utf-8") as f:
        questions_raw = json.load(f)

    questions = {}
    for q in questions_raw:
        qid = q.get("id") or q.get("question_id")
        if qid in TARGET_QUESTIONS:
            questions[qid] = q.get("question")

    return ground_truth, questions


def evaluate():
    ground_truth, questions = load_evaluation_data()

    print("=" * 80)
    print("UNIFIED PIPELINE EVALUATION: Q10, Q13, Q19")
    print("=" * 80)

    # Initialize components
    print("\nInitializing retrievers and models...")
    dense_retriever = DenseRetriever()
    bm25_retriever = BM25Retriever()
    hybrid_retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
    )
    confidence_evaluator = ConfidenceEvaluator()
    query_rewriter = QueryRewriter()
    reranker = CrossEncoderReranker(model_name=RERANKER_MODEL)

    summary_results = []

    for qid in TARGET_QUESTIONS:
        query = questions[qid]
        gt_item = ground_truth.get(qid, {})
        expected_chunks = gt_item.get("relevant_chunks", [])

        print("\n" + "#" * 80)
        print(f"QUESTION {qid}: {query}")
        print(f"Expected Chunks ({len(expected_chunks)}): {expected_chunks}")
        print("#" * 80)

        # ----------------------------------------------------
        # 1. Dense Retrieval
        # ----------------------------------------------------
        t0 = time.perf_counter()
        dense_candidates = dense_retriever.retrieve(query, top_k=20)
        dense_latency = (time.perf_counter() - t0) * 1000

        # ----------------------------------------------------
        # 2. BM25 Retrieval
        # ----------------------------------------------------
        t0 = time.perf_counter()
        bm25_candidates = bm25_retriever.retrieve(query, top_k=20)
        bm25_latency = (time.perf_counter() - t0) * 1000

        # ----------------------------------------------------
        # 3. Hybrid RRF Retrieval
        # ----------------------------------------------------
        t0 = time.perf_counter()
        hybrid_candidates = hybrid_retriever.fusion.fuse(
            [dense_candidates, bm25_candidates], top_k=20
        )
        hybrid_latency = dense_latency + bm25_latency + ((time.perf_counter() - t0) * 1000)

        # ----------------------------------------------------
        # 4. Hybrid + Adaptive Query Rewriting
        # ----------------------------------------------------
        t0 = time.perf_counter()
        conf = confidence_evaluator.evaluate(hybrid_candidates)
        adaptive_triggered = not conf.is_confident
        rewritten_query = query

        if adaptive_triggered:
            rw_res = query_rewriter.rewrite(query)
            if rw_res.success and not rw_res.fallback_used and rw_res.rewritten_query:
                rewritten_query = rw_res.rewritten_query
                d_rw = dense_retriever.retrieve(rewritten_query, top_k=20)
                b_rw = bm25_retriever.retrieve(rewritten_query, top_k=20)
                f_rw = hybrid_retriever.fusion.fuse([d_rw, b_rw], top_k=20)
                adaptive_candidates = merge_candidate_pools(hybrid_candidates, f_rw, limit=20)
            else:
                adaptive_candidates = hybrid_candidates
        else:
            adaptive_candidates = hybrid_candidates
        adaptive_latency = (time.perf_counter() - t0) * 1000 + hybrid_latency

        # ----------------------------------------------------
        # 5. Hybrid + Cross-Encoder Reranker
        # ----------------------------------------------------
        t0 = time.perf_counter()
        reranked_candidates = reranker.rerank(query, hybrid_candidates, top_n=20)
        rerank_latency = (time.perf_counter() - t0) * 1000

        methods = [
            ("Dense (BGE-M3)", dense_candidates, dense_latency),
            ("BM25 (Okapi)", bm25_candidates, bm25_latency),
            ("Hybrid (RRF)", hybrid_candidates, hybrid_latency),
            ("Hybrid + Adaptive Rewriting", adaptive_candidates, adaptive_latency),
            ("Hybrid + BGE Reranker", reranked_candidates, hybrid_latency + rerank_latency),
        ]

        q_report = {
            "qid": qid,
            "query": query,
            "expected": expected_chunks,
            "adaptive_decision": {
                "triggered": adaptive_triggered,
                "reason": conf.reason,
                "rewritten_query": rewritten_query if adaptive_triggered else None,
            },
            "methods": {},
        }

        for name, cands, latency in methods:
            cand_ids_20 = [c.chunk_id for c in cands[:20]]
            cand_ids_10 = [c.chunk_id for c in cands[:10]]
            cand_ids_5 = [c.chunk_id for c in cands[:5]]

            retrieved_in_5 = [cid for cid in expected_chunks if cid in cand_ids_5]
            retrieved_in_10 = [cid for cid in expected_chunks if cid in cand_ids_10]
            retrieved_in_20 = [cid for cid in expected_chunks if cid in cand_ids_20]

            hit5 = len(retrieved_in_5) > 0
            hit10 = len(retrieved_in_10) > 0
            hit20 = len(retrieved_in_20) > 0

            q_report["methods"][name] = {
                "latency_ms": latency,
                "hit@5": hit5,
                "hit@10": hit10,
                "hit@20": hit20,
                "retrieved_in_5": retrieved_in_5,
                "retrieved_in_20": retrieved_in_20,
                "top5_chunks": cand_ids_5,
            }

            print(f"\n--- {name} --- (Latency: {latency:.1f}ms)")
            print(f"  Hit@5: {hit5} (Found: {retrieved_in_5}/{len(expected_chunks)})")
            print(f"  Hit@20: {hit20} (Found: {retrieved_in_20}/{len(expected_chunks)})")
            print(f"  Top 5: {cand_ids_5}")

        summary_results.append(q_report)

    # Print summary table
    print("\n" + "=" * 90)
    print("SUMMARY OF BENCHMARK FOR Q10, Q13, Q19")
    print("=" * 90)
    print(f"{'QID':<6} | {'Pipeline Configuration':<32} | {'Hit@5':<6} | {'Hit@20':<6} | {'Found / Total':<14} | {'Latency':<10}")
    print("-" * 90)

    for item in summary_results:
        qid = item["qid"]
        n_exp = len(item["expected"])
        for name, m in item["methods"].items():
            f5 = len(m["retrieved_in_5"])
            f20 = len(m["retrieved_in_20"])
            found_str = f"{f5}/{n_exp} (in top 5)"
            print(f"{qid:<6} | {name:<32} | {str(m['hit@5']):<6} | {str(m['hit@20']):<6} | {found_str:<14} | {m['latency_ms']:.1f} ms")
        print("-" * 90)

    # Save results to json
    out_file = PROJECT_ROOT / "reports" / "evaluation_q10_q13_q19_summary.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_results, f, indent=2)
    print(f"\nSaved detailed evaluation metrics to: {out_file}")


if __name__ == "__main__":
    evaluate()
