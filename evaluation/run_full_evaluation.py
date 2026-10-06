#!/usr/bin/env python3
"""Unified Terminal RAG Evaluation Runner for Cybersecurity RAG.

Executes and reports on all three levels of RAG evaluation:
1. Retrieval Evaluation (Dense, BM25, RRF/Hybrid, Cross-Encoder Reranking)
2. Generation Evaluation (Faithfulness, Answer Relevance, Correctness, Groundedness, Citation Accuracy)
3. End-to-End Evaluation (Success Rate, Grounded Answers, Citations, Overall E2E Score)
"""

import argparse
import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# Bootstrap project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_REAL_STDOUT = sys.stdout


def print_progress(msg: str) -> None:
    """Print progress directly to the terminal stdout without being swallowed by inner redirects."""
    try:
        _REAL_STDOUT.write(msg + "\n")
        _REAL_STDOUT.flush()
    except Exception:
        sys.__stdout__.write(msg + "\n")
        sys.__stdout__.flush()


@contextlib.contextmanager
def silence_stdout(active: bool = True):
    """Context manager to suppress intermediate prints and tqdm progress unless verbose."""
    if not active:
        yield
    else:
        saved_stdout = sys.stdout
        saved_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            yield
        finally:
            sys.stdout = saved_stdout
            sys.stderr = saved_stderr


from app.core.config import settings
from app.generation.providers.groq_provider import GroqProvider
from app.pipeline.engine import RAGEngine
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import reciprocal_rank_fusion


# ============================================================
# METRICS COMPUTATION HELPERS
# ============================================================

def calc_hit_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> int:
    """Return 1 if at least one relevant chunk appears in top-k, else 0."""
    return 1 if any(cid in relevant for cid in retrieved[:k]) else 0


def calc_precision_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> float:
    """Return the proportion of relevant chunks in top-k."""
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    return sum(1 for cid in top_k if cid in relevant) / len(top_k)


def calc_mrr(retrieved: Sequence[str], relevant: Set[str]) -> float:
    """Return the reciprocal rank of the first relevant chunk."""
    for rank, cid in enumerate(retrieved, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def parse_ground_truth_ids(gt_item: Any) -> Set[str]:
    """Extract set of relevant chunk IDs from ground-truth entry."""
    if isinstance(gt_item, dict):
        ids = gt_item.get("relevant_chunks") or gt_item.get("relevant_chunk_ids") or []
        return set(str(cid) for cid in ids)
    elif isinstance(gt_item, list):
        return set(str(cid) for cid in gt_item)
    return set()


def extract_citations(text: str) -> List[int]:
    """Extract 1-based source indices from citation tags like [Source 1] or [Source 2]."""
    matches = re.findall(r"\[Source[\s\u202f]*(\d+)\]", text, re.IGNORECASE)
    return [int(m) for m in matches]


def format_score(val: Optional[float], is_percent: bool = True) -> str:
    """Format numerical score or return 'NOT AVAILABLE' if missing/None."""
    if val is None:
        return "NOT AVAILABLE"
    if is_percent:
        return f"{val:.2f}%"
    return f"{val:.4f}"


# ============================================================
# RETRIEVAL EVALUATION (LEVEL 1)
# ============================================================

def run_retrieval_evaluation(
    questions: List[Dict[str, Any]],
    ground_truth: Dict[str, Any],
    bm25_ground_truth: Dict[str, Any],
    verbose: bool = False,
) -> Dict[str, Dict[str, float]]:
    """Evaluate Dense, BM25, RRF Hybrid, and Cross-Encoder Reranker."""
    print_progress("[1/3] Running retrieval evaluation...")

    with silence_stdout(not verbose):
        dense_retriever = DenseRetriever()
        bm25_retriever = BM25Retriever()
        reranker = CrossEncoderReranker()

    dense_metrics = []
    bm25_metrics = []
    rrf_metrics = []
    rerank_metrics = []
    bm25_cached_results: Dict[int, Any] = {}

    try:
        print_progress("  Evaluating Dense, BM25, RRF, and Reranking (15 benchmark questions)...")
        # Evaluate standard 15 benchmark questions for Dense, RRF, and Reranking
        for idx, q_item in enumerate(questions[:15]):
            qid = q_item["id"]
            query = q_item["question"]
            rel_ids = parse_ground_truth_ids(ground_truth.get(qid, []))

            # 1. Dense retrieval (Top-20)
            with silence_stdout(not verbose):
                dense_res = dense_retriever.retrieve(query, top_k=20)
            dense_ids = [c.chunk_id for c in dense_res]
            dense_metrics.append({
                "hit1": calc_hit_at_k(dense_ids, rel_ids, 1),
                "hit3": calc_hit_at_k(dense_ids, rel_ids, 3),
                "hit5": calc_hit_at_k(dense_ids, rel_ids, 5),
                "prec5": calc_precision_at_k(dense_ids, rel_ids, 5),
                "mrr": calc_mrr(dense_ids[:5], rel_ids),
            })

            # 2. BM25 retrieval (Top-20) - cache results to avoid duplicate execution
            with silence_stdout(not verbose):
                bm25_res = bm25_retriever.retrieve(query, top_k=20)
            bm25_cached_results[idx] = bm25_res

            # 3. RRF Fusion (Top-20)
            rrf_res = reciprocal_rank_fusion([dense_res, bm25_res], top_k=20)
            rrf_ids = [c.chunk_id for c in rrf_res]
            rrf_metrics.append({
                "hit1": calc_hit_at_k(rrf_ids, rel_ids, 1),
                "hit3": calc_hit_at_k(rrf_ids, rel_ids, 3),
                "hit5": calc_hit_at_k(rrf_ids, rel_ids, 5),
                "prec5": calc_precision_at_k(rrf_ids, rel_ids, 5),
                "mrr": calc_mrr(rrf_ids, rel_ids),
            })

            # 4. Cross-Encoder Reranking (Top-5)
            with silence_stdout(not verbose):
                rerank_res = reranker.rerank(query, rrf_res, top_n=5)
            rerank_ids = [c.chunk_id for c in rerank_res]
            rerank_metrics.append({
                "hit1": calc_hit_at_k(rerank_ids, rel_ids, 1),
                "hit3": calc_hit_at_k(rerank_ids, rel_ids, 3),
                "hit5": calc_hit_at_k(rerank_ids, rel_ids, 5),
                "prec5": calc_precision_at_k(rerank_ids, rel_ids, 5),
                "mrr": calc_mrr(rerank_ids, rel_ids),
            })

        print_progress("  Evaluating standalone BM25 benchmark...")
        # Evaluate BM25 standalone against its ground-truth benchmark (matching evaluate_bm25.py)
        # Reuses cached results for indices 0..14 to avoid redundant BM25 searches
        for idx in range(len(questions)):
            q_key = f"Q{idx + 1}"
            rel_ids = parse_ground_truth_ids(bm25_ground_truth.get(q_key, []))
            if idx in bm25_cached_results:
                bm25_res = bm25_cached_results[idx]
            else:
                query = questions[idx]["question"]
                with silence_stdout(not verbose):
                    bm25_res = bm25_retriever.retrieve(query, top_k=20)
            bm25_ids = [c.chunk_id for c in bm25_res]
            bm25_metrics.append({
                "hit1": calc_hit_at_k(bm25_ids, rel_ids, 1),
                "hit3": calc_hit_at_k(bm25_ids, rel_ids, 3),
                "hit5": calc_hit_at_k(bm25_ids, rel_ids, 5),
                "prec5": calc_precision_at_k(bm25_ids, rel_ids, 5),
                "mrr": calc_mrr(bm25_ids, rel_ids),
            })

    finally:
        dense_retriever.close()

    def aggregate(items: List[Dict[str, float]]) -> Dict[str, float]:
        n = max(1, len(items))
        return {
            "hit1": sum(x["hit1"] for x in items) / n * 100.0,
            "hit3": sum(x["hit3"] for x in items) / n * 100.0,
            "hit5": sum(x["hit5"] for x in items) / n * 100.0,
            "prec5": sum(x["prec5"] for x in items) / n * 100.0,
            "mrr": sum(x["mrr"] for x in items) / n,
        }

    return {
        "dense": aggregate(dense_metrics),
        "bm25": aggregate(bm25_metrics) if bm25_metrics else aggregate(dense_metrics),
        "rrf": aggregate(rrf_metrics),
        "reranker": aggregate(rerank_metrics),
    }


# ============================================================
# GENERATION & END-TO-END EVALUATION (LEVELS 2 & 3)
# ============================================================

def judge_answer_quality(
    judge_llm: Optional[GroqProvider],
    question: str,
    context: str,
    answer: str,
    citations: List[int],
    num_sources: int,
) -> Tuple[Dict[str, Optional[float]], Optional[str]]:
    """Evaluate Faithfulness, Relevance, Correctness, Groundedness, and Citation Accuracy.

    Returns:
        Tuple of (metrics_dict, error_message_or_None).
        If the judge fails or metrics are missing, metric values are None (NOT AVAILABLE).
        Never returns fabricated or hardcoded numerical scores.
    """
    # 1. Citation Accuracy (deterministic calculation from citation references)
    if citations and num_sources > 0:
        valid = [c for c in citations if 1 <= c <= num_sources]
        citation_acc = (len(valid) / len(citations)) * 100.0
    else:
        citation_acc = 0.0

    # 2. LLM-as-a-Judge evaluation
    if judge_llm is None:
        return {
            "faithfulness": None,
            "answer_relevance": None,
            "correctness": None,
            "groundedness": None,
            "citation_accuracy": citation_acc,
        }, "LLM judge unavailable (GroqProvider not initialized)."

    judge_prompt = f"""You are a strict cybersecurity evaluation judge evaluating a RAG answer.
Score the following metrics on a continuous scale from 0.0 to 100.0 based ONLY on the context:

1. faithfulness: Are the claims in the answer strictly supported by the context without unsupported claims?
2. answer_relevance: Does the answer directly and concisely address the question?
3. correctness: Is the factual content accurate and aligned with the provided context?
4. groundedness: What percentage of factual statements are directly verifiable in the context?

USER QUESTION:
{question}

RETRIEVED CONTEXT:
{context[:2500]}

GENERATED ANSWER:
{answer}

Respond ONLY with a valid JSON object matching this schema:
{{"faithfulness": <score 0.0-100.0>, "answer_relevance": <score 0.0-100.0>, "correctness": <score 0.0-100.0>, "groundedness": <score 0.0-100.0>}}"""

    try:
        raw = judge_llm.generate(judge_prompt, temperature=0.0, max_tokens=256)
    except Exception as e:
        return {
            "faithfulness": None,
            "answer_relevance": None,
            "correctness": None,
            "groundedness": None,
            "citation_accuracy": citation_acc,
        }, f"LLM judge request failed: {e}"

    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return {
            "faithfulness": None,
            "answer_relevance": None,
            "correctness": None,
            "groundedness": None,
            "citation_accuracy": citation_acc,
        }, "LLM judge failed to return valid JSON."

    try:
        data = json.loads(match.group())
    except Exception as e:
        return {
            "faithfulness": None,
            "answer_relevance": None,
            "correctness": None,
            "groundedness": None,
            "citation_accuracy": citation_acc,
        }, f"LLM judge returned malformed JSON: {e}"

    scores: Dict[str, Optional[float]] = {}
    missing_metrics = []
    for metric_name in ["faithfulness", "answer_relevance", "correctness", "groundedness"]:
        val = data.get(metric_name)
        if val is not None:
            try:
                scores[metric_name] = float(val)
            except (ValueError, TypeError):
                scores[metric_name] = None
                missing_metrics.append(metric_name)
        else:
            scores[metric_name] = None
            missing_metrics.append(metric_name)

    scores["citation_accuracy"] = citation_acc

    err = None
    if missing_metrics:
        err = f"LLM judge returned missing or invalid metric(s): {', '.join(missing_metrics)}."

    return scores, err


def run_e2e_and_generation_evaluation(
    eval_questions: List[Dict[str, Any]],
    e2e_count: int = 5,
    verbose: bool = False,
) -> Tuple[Dict[str, Optional[float]], Dict[str, Any], List[str]]:
    """Run End-to-End RAG questions and evaluate Generation Quality."""
    engine = None
    with silence_stdout(not verbose):
        engine = RAGEngine()

    judge_llm = None
    generation_errors: List[str] = []
    try:
        judge_llm = GroqProvider()
    except Exception as e:
        judge_llm = None
        generation_errors.append(f"LLM judge initialization failed: {e}")

    scores_list: List[Dict[str, Optional[float]]] = []
    questions_evaluated = 0
    successful_answers = 0
    grounded_answers = 0
    answers_with_citations = 0

    target_questions = eval_questions[:e2e_count]

    try:
        for idx, q_item in enumerate(target_questions, start=1):
            question = q_item["question"]
            print_progress(f"  Evaluating question {idx}/{len(target_questions)}...")
            questions_evaluated += 1

            try:
                with silence_stdout(not verbose):
                    response = engine.query(question, stream=False)
                answer = response.answer.strip()

                if answer:
                    successful_answers += 1

                citations = extract_citations(answer)
                if citations:
                    answers_with_citations += 1

                # Build context string for judging
                context = "\n\n".join(
                    f"SOURCE {s_idx+1}: {chunk.text}"
                    for s_idx, chunk in enumerate(response.sources)
                )

                # Quality judging
                with silence_stdout(not verbose):
                    scores, err = judge_answer_quality(
                        judge_llm=judge_llm,
                        question=question,
                        context=context,
                        answer=answer,
                        citations=citations,
                        num_sources=len(response.sources),
                    )

                if err:
                    generation_errors.append(err)

                scores_list.append(scores)

                if scores.get("groundedness") is not None and scores["groundedness"] >= 70.0:
                    grounded_answers += 1

            except Exception as e:
                err_msg = f"Question {idx} pipeline execution failed: {e}"
                generation_errors.append(err_msg)
                if verbose:
                    print(f"Error evaluating '{question}': {e}", file=sys.stderr)
    finally:
        if engine:
            engine.close()

    # Aggregate Generation Quality metrics without fabricating missing values
    avg_gen: Dict[str, Optional[float]] = {}
    for metric_name in [
        "faithfulness",
        "answer_relevance",
        "correctness",
        "groundedness",
        "citation_accuracy",
    ]:
        valid_vals = [
            s[metric_name]
            for s in scores_list
            if s.get(metric_name) is not None
        ]
        if valid_vals:
            avg_gen[metric_name] = sum(valid_vals) / len(valid_vals)
        else:
            avg_gen[metric_name] = None

    # Aggregate End-to-End Quality
    has_groundedness = any(s.get("groundedness") is not None for s in scores_list)
    success_rate = (successful_answers / max(1, questions_evaluated)) * 100.0
    citation_rate = (answers_with_citations / max(1, questions_evaluated)) * 100.0

    if has_groundedness:
        grounded_count: Optional[int] = grounded_answers
        grounded_rate = (grounded_answers / max(1, questions_evaluated)) * 100.0
        overall_e2e_score: Optional[float] = (success_rate + grounded_rate + citation_rate) / 3.0
    else:
        grounded_count = None
        overall_e2e_score = None

    e2e_summary = {
        "questions_evaluated": questions_evaluated,
        "successful_answers": successful_answers,
        "grounded_answers": grounded_count,
        "answers_with_citations": answers_with_citations,
        "overall_e2e_score": overall_e2e_score,
    }

    return avg_gen, e2e_summary, generation_errors


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Unified Terminal RAG Evaluation Runner for Cybersecurity RAG"
    )
    parser.add_argument(
        "--e2e-count",
        type=int,
        default=5,
        help="Number of questions to evaluate for End-to-End and Generation (default: 5)",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip LLM generation and E2E evaluation (retrieval only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose execution logs",
    )
    args = parser.parse_args()

    # Load benchmark files
    eval_q_file = settings.evaluation_dir / "evaluation_questions.json"
    eval_gt_file = settings.evaluation_dir / "retrieval_ground_truth.json"
    bm25_gt_file = settings.evaluation_dir / "ground_truth.json"

    with open(eval_q_file, "r", encoding="utf-8") as f:
        questions = json.load(f)

    with open(eval_gt_file, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    with open(bm25_gt_file, "r", encoding="utf-8") as f:
        bm25_gt = json.load(f)

    # 1. Run Level 1: Retrieval Evaluation
    retrieval_results = run_retrieval_evaluation(
        questions=questions,
        ground_truth=ground_truth,
        bm25_ground_truth=bm25_gt,
        verbose=args.verbose,
    )

    # 2. Run Levels 2 & 3: Generation & End-to-End Evaluation
    if not args.skip_generation:
        print_progress("[2/3] Running generation evaluation...")
        print_progress("[3/3] Running end-to-end evaluation...")
        gen_results, e2e_results, generation_errors = run_e2e_and_generation_evaluation(
            eval_questions=questions,
            e2e_count=args.e2e_count,
            verbose=args.verbose,
        )
    else:
        print_progress("[2/3] Skipping generation evaluation (--skip-generation enabled)...")
        print_progress("[3/3] Skipping end-to-end evaluation (--skip-generation enabled)...")
        generation_errors = ["Generation evaluation skipped via --skip-generation."]
        gen_results = {
            "faithfulness": None,
            "answer_relevance": None,
            "correctness": None,
            "groundedness": None,
            "citation_accuracy": None,
        }
        e2e_results = {
            "questions_evaluated": 0,
            "successful_answers": 0,
            "grounded_answers": None,
            "answers_with_citations": 0,
            "overall_e2e_score": None,
        }

    # Calculate overall summary scores
    retrieval_quality = (retrieval_results["reranker"]["hit5"] + retrieval_results["reranker"]["mrr"] * 100.0) / 2.0

    # Generation Quality is calculated only if genuine LLM scores are available
    llm_scores = [
        v for k, v in gen_results.items()
        if k in ("faithfulness", "answer_relevance", "correctness", "groundedness") and v is not None
    ]
    if llm_scores:
        valid_scores = [v for v in gen_results.values() if v is not None]
        generation_quality: Optional[float] = sum(valid_scores) / len(valid_scores)
    else:
        generation_quality = None

    e2e_quality = e2e_results["overall_e2e_score"]

    # ============================================================
    # TERMINAL REPORT RENDERING
    # ============================================================
    d = retrieval_results["dense"]
    b = retrieval_results["bm25"]
    r = retrieval_results["rrf"]
    rk = retrieval_results["reranker"]

    print()
    print("=" * 60)
    print("              CYBERSECURITY RAG EVALUATION")
    print("=" * 60)
    print()
    print("[1] RETRIEVAL EVALUATION")
    print("-" * 60)
    print()
    print("Dense Retrieval")
    print(f"  Hit@1          : {d['hit1']:.2f}%")
    print(f"  Hit@3          : {d['hit3']:.2f}%")
    print(f"  Hit@5          : {d['hit5']:.2f}%")
    print(f"  Precision@5    : {d['prec5']:.2f}%")
    print(f"  MRR            : {d['mrr']:.4f}")
    print()
    print("BM25 Retrieval")
    print(f"  Hit@1          : {b['hit1']:.2f}%")
    print(f"  Hit@3          : {b['hit3']:.2f}%")
    print(f"  Hit@5          : {b['hit5']:.2f}%")
    print(f"  Precision@5    : {b['prec5']:.2f}%")
    print(f"  MRR            : {b['mrr']:.4f}")
    print()
    print("RRF / Hybrid Retrieval")
    print(f"  Hit@1          : {r['hit1']:.2f}%")
    print(f"  Hit@3          : {r['hit3']:.2f}%")
    print(f"  Hit@5          : {r['hit5']:.2f}%")
    print(f"  Precision@5    : {r['prec5']:.2f}%")
    print(f"  MRR            : {r['mrr']:.4f}")
    print()
    print("Cross-Encoder Reranking")
    print(f"  Hit@1          : {rk['hit1']:.2f}%")
    print(f"  Hit@3          : {rk['hit3']:.2f}%")
    print(f"  Hit@5          : {rk['hit5']:.2f}%")
    print(f"  Precision@5    : {rk['prec5']:.2f}%")
    print(f"  MRR            : {rk['mrr']:.4f}")
    print()
    print()
    print("[2] GENERATION EVALUATION")
    print("-" * 60)
    print()
    if generation_errors:
        print("Generation evaluator error:")
        for err_msg in dict.fromkeys(generation_errors):
            print(f"  {err_msg}")
        print()
    print(f"Faithfulness       : {format_score(gen_results['faithfulness'])}")
    print(f"Answer Relevance   : {format_score(gen_results['answer_relevance'])}")
    print(f"Correctness        : {format_score(gen_results['correctness'])}")
    print(f"Groundedness       : {format_score(gen_results['groundedness'])}")
    print(f"Citation Accuracy  : {format_score(gen_results['citation_accuracy'])}")
    print()
    print()
    print("[3] END-TO-END EVALUATION")
    print("-" * 60)
    print()
    print(f"Questions Evaluated     : {e2e_results['questions_evaluated']}")
    print(f"Successful Answers     : {e2e_results['successful_answers']}")
    if e2e_results['grounded_answers'] is not None:
        print(f"Grounded Answers       : {e2e_results['grounded_answers']}")
    else:
        print(f"Grounded Answers       : NOT AVAILABLE")
    print(f"Answers With Citations : {e2e_results['answers_with_citations']}")
    print()
    print(f"Overall E2E Score       : {format_score(e2e_results['overall_e2e_score'])}")
    print()
    print()
    print("=" * 60)
    print("                    EVALUATION SUMMARY")
    print("=" * 60)
    print()
    print(f"Retrieval Quality  : {format_score(retrieval_quality)}")
    print(f"Generation Quality : {format_score(generation_quality)}")
    print(f"End-to-End Quality : {format_score(e2e_quality)}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
