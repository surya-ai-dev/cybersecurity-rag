"""Interactive Diagnostic: Inspect Dense Retrieval and BGE-Reranker (v2-m3) Pipeline.

Executes and visualizes the complete two-stage retrieval pipeline:
1. Dense semantic search (BAAI/bge-m3 via Qdrant) retrieving Top 20 candidates.
2. Cross-Encoder reranking (BAAI/bge-reranker-v2-m3) rescoring all 20 candidates.
3. Comparative composition analysis (Dense Top-5 vs Reranked Top-5).
4. Ground-truth relevance evaluation and failure analysis.

Usage:
    # Inspect by Question ID (e.g. Q10):
    python scripts/inspect_bge_reranking.py -q Q10

    # Non-interactive confirmation (auto-proceed):
    python scripts/inspect_bge_reranking.py -q Q10 -y

    # Inspect a custom query:
    python scripts/inspect_bge_reranking.py --query "What are the security implications of cloud storage?"

    # Interactive loop mode:
    python scripts/inspect_bge_reranking.py
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Safe UTF-8 console output for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.models import RetrievedChunk
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import CrossEncoderReranker

EMBEDDING_MODEL = "BAAI/bge-m3"
COLLECTION_NAME = "cybersecurity_chunks_bge_m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_TOP_CANDIDATES = 20
DEFAULT_TOP_FINAL = 5

QUESTIONS_FILE = PROJECT_ROOT / "data" / "evaluation" / "evaluation_questions.json"
BASELINE_GT_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_current.json"
ADDITIONAL_GT_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_additional_20.json"


# =========================================================================
# GROUND TRUTH & QUESTION LOADERS
# =========================================================================

def load_ground_truth_data() -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Load merged ground truth and questions mapping.

    Returns:
        gt_dict: Mapping of question_id -> ground truth record.
        questions_dict: Mapping of question_id -> question text.
    """
    gt_dict: Dict[str, Any] = {}
    if BASELINE_GT_FILE.exists():
        with open(BASELINE_GT_FILE, "r", encoding="utf-8") as f:
            gt_dict.update(json.load(f))
    if ADDITIONAL_GT_FILE.exists():
        with open(ADDITIONAL_GT_FILE, "r", encoding="utf-8") as f:
            gt_dict.update(json.load(f))

    questions_dict: Dict[str, str] = {}
    if QUESTIONS_FILE.exists():
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            for item in json.load(f):
                qid = item.get("id")
                qtext = item.get("question")
                if qid and qtext:
                    questions_dict[qid] = qtext

    # Backfill question text from ground truth if needed
    for qid, entry in gt_dict.items():
        if qid not in questions_dict and "question" in entry:
            questions_dict[qid] = entry["question"]

    return gt_dict, questions_dict


def resolve_query(
    user_input: str,
    gt_dict: Dict[str, Any],
    questions_dict: Dict[str, str],
) -> Tuple[str, Optional[str], Optional[Dict[str, Any]]]:
    """Resolve user input to question text, question ID, and ground truth record.

    Args:
        user_input: Question ID (e.g. 'Q10') or raw query text.
        gt_dict: Merged ground truth dictionary.
        questions_dict: Question ID to text mapping.

    Returns:
        query_text: The actual query to evaluate.
        question_id: The resolved question ID (or None if custom query).
        gt_record: The ground truth record (or None if no match).
    """
    cleaned = user_input.strip()
    upper_id = cleaned.upper()

    # Case 1: Direct question ID match (e.g. Q10, q10)
    if upper_id in questions_dict or upper_id in gt_dict:
        qtext = questions_dict.get(upper_id) or gt_dict[upper_id].get("question", cleaned)
        return qtext, upper_id, gt_dict.get(upper_id)

    # Case 2: Exact question text match in dataset
    for qid, qtext in questions_dict.items():
        if qtext.strip().lower() == cleaned.lower():
            return qtext, qid, gt_dict.get(qid)

    # Case 3: Custom query
    return cleaned, None, None


# =========================================================================
# DISPLAY & FORMATTING HELPERS
# =========================================================================

def format_text_excerpt(text: str, max_length: int = 170) -> str:
    """Format and collapse multiline text into a clean single-line excerpt."""
    collapsed = " ".join(text.split())
    if len(collapsed) > max_length:
        return collapsed[:max_length].rstrip() + "..."
    return collapsed


def display_candidates(
    candidates: List[RetrievedChunk],
    relevant_chunks: List[str],
    title: str = "DENSE RETRIEVAL TOP 20 CANDIDATES",
    query: str = "",
    latency_ms: float = 0.0,
) -> None:
    """Display candidate chunks in a detailed numbered list."""
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    if query:
        print(f"Query           : {query}")
    print(f"Candidates Count: {len(candidates)} chunks retrieved in {latency_ms:.1f} ms")
    print("-" * 100)

    for rank, chunk in enumerate(candidates, start=1):
        is_rel = chunk.chunk_id in relevant_chunks
        rel_tag = " ★ [GROUND-TRUTH RELEVANT]" if is_rel else ""
        doc_id = chunk.metadata.document_id if chunk.metadata else "Unknown"
        section = chunk.metadata.section if chunk.metadata else "Unknown"
        source = chunk.metadata.source_file if chunk.metadata else "Unknown"
        score = chunk.dense_score if chunk.dense_score is not None else chunk.score

        print(f"\n[{rank:2d}] Score: {score:.6f} | Chunk ID: {chunk.chunk_id}{rel_tag}")
        print(f"     Document: {doc_id} | Section: {section} | File: {source}")
        print(f"     Excerpt : \"{format_text_excerpt(chunk.text)}\"")

    print("\n" + "-" * 100)


def display_reranked_table(
    reranked_chunks: List[RetrievedChunk],
    dense_ranks: Dict[str, int],
    relevant_chunks: List[str],
    latency_s: float,
) -> None:
    """Display table of all 20 candidates sorted by reranker score with rank shifts."""
    print("\n" + "=" * 100)
    print(f"BGE RERANKED CANDIDATES TABLE (Model: {RERANKER_MODEL})")
    print("=" * 100)
    print(f"Scored {len(reranked_chunks)} candidate pairs on CPU in {latency_s:.2f} s ({latency_s * 1000 / len(reranked_chunks):.1f} ms/pair)")
    print("-" * 100)
    print(f"{'Rank':<5} {'Dense':<7} {'Movement':<11} {'Score':<10} {'Chunk ID':<30} {'Relevance':<13} {'Document'}")
    print("-" * 100)

    for r_rank, chunk in enumerate(reranked_chunks, start=1):
        cid = chunk.chunk_id
        d_rank = dense_ranks.get(cid, 0)
        score = chunk.reranker_score if chunk.reranker_score is not None else chunk.score
        is_rel = cid in relevant_chunks

        # Calculate movement
        diff = d_rank - r_rank
        if diff > 0:
            mov_str = f"▲ +{diff}"
        elif diff < 0:
            mov_str = f"▼ -{abs(diff)}"
        else:
            mov_str = "═  0"

        rel_str = "★ RELEVANT" if is_rel else ""
        doc_id = chunk.metadata.document_id if chunk.metadata else "Unknown"

        print(
            f"{r_rank:<5d} [{d_rank:2d}]   {mov_str:<11} {score:<10.4f} "
            f"{cid:<30} {rel_str:<13} {doc_id}"
        )

    print("-" * 100)


def display_final_top5(
    reranked_chunks: List[RetrievedChunk],
    dense_ranks: Dict[str, int],
    relevant_chunks: List[str],
    top_k: int = 5,
) -> None:
    """Display the final reranked Top-5 chunks prominently."""
    print("\n" + "=" * 100)
    print(f"FINAL BGE-RERANKED TOP {top_k}")
    print("=" * 100)

    for rank, chunk in enumerate(reranked_chunks[:top_k], start=1):
        cid = chunk.chunk_id
        d_rank = dense_ranks.get(cid, 0)
        score = chunk.reranker_score if chunk.reranker_score is not None else chunk.score
        is_rel = cid in relevant_chunks
        rel_tag = " ★ [GROUND-TRUTH RELEVANT]" if is_rel else ""
        doc_id = chunk.metadata.document_id if chunk.metadata else "Unknown"
        section = chunk.metadata.section if chunk.metadata else "Unknown"

        print(f"\n[Rank {rank}] Score: {score:.4f} (Original Dense Rank: [{d_rank}]) | ID: {cid}{rel_tag}")
        print(f"          Document: {doc_id} | Section: {section}")
        print(f"          Excerpt : \"{format_text_excerpt(chunk.text, max_length=200)}\"")

    print("\n" + "-" * 100)


def display_composition_comparison(
    dense_candidates: List[RetrievedChunk],
    reranked_chunks: List[RetrievedChunk],
    dense_ranks: Dict[str, int],
    relevant_chunks: List[str],
    top_k: int = 5,
) -> None:
    """Compare the composition of Dense Top-5 vs Reranked Top-5."""
    dense_top_cids = [c.chunk_id for c in dense_candidates[:top_k]]
    rerank_top_cids = [c.chunk_id for c in reranked_chunks[:top_k]]

    rerank_map = {c.chunk_id: (idx, c) for idx, c in enumerate(reranked_chunks, start=1)}
    dense_map = {c.chunk_id: (idx, c) for idx, c in enumerate(dense_candidates, start=1)}

    entered = [cid for cid in rerank_top_cids if cid not in dense_top_cids]
    left = [cid for cid in dense_top_cids if cid not in rerank_top_cids]
    retained = [cid for cid in rerank_top_cids if cid in dense_top_cids]

    print("\n" + "=" * 100)
    print(f"TOP-{top_k} COMPOSITION COMPARISON (Dense Baseline vs BGE Reranker)")
    print("=" * 100)

    print(f"\n▲ Entered Top-{top_k} ({len(entered)} chunks promoted into final list):")
    if entered:
        for cid in entered:
            r_idx, chunk = rerank_map[cid]
            d_idx = dense_ranks.get(cid, 0)
            score = chunk.reranker_score or chunk.score
            is_rel = cid in relevant_chunks
            rel_marker = " ★ [RELEVANT]" if is_rel else ""
            print(f"    + {cid}{rel_marker}")
            print(f"      Original Dense Rank: [{d_idx:2d}] -> Reranked Rank: [{r_idx}] | Score: {score:.4f}")
    else:
        print("    (None - Top-5 set remained identical)")

    print(f"\n▼ Left Top-{top_k} ({len(left)} chunks demoted out of final list):")
    if left:
        for cid in left:
            d_idx, chunk = dense_map[cid]
            r_idx = next((i for i, c in enumerate(reranked_chunks, start=1) if c.chunk_id == cid), None)
            score = chunk.dense_score or chunk.score
            is_rel = cid in relevant_chunks
            rel_marker = " ★ [RELEVANT]" if is_rel else ""
            print(f"    - {cid}{rel_marker}")
            print(f"      Original Dense Rank: [{d_idx:2d}] -> Dropped to Rank: [{r_idx}] (Dense Score: {score:.4f})")
    else:
        print("    (None - No chunks left Top-5)")

    print(f"\n═ Retained in Top-{top_k} ({len(retained)} chunks preserved):")
    for cid in retained:
        r_idx, chunk = rerank_map[cid]
        d_idx = dense_ranks.get(cid, 0)
        score = chunk.reranker_score or chunk.score
        is_rel = cid in relevant_chunks
        rel_marker = " ★ [RELEVANT]" if is_rel else ""
        print(f"    = {cid}{rel_marker} (Dense Rank: [{d_idx:2d}] -> Reranked Rank: [{r_idx}], Score: {score:.4f})")

    print("\n" + "-" * 100)


def display_ground_truth_analysis(
    question_id: Optional[str],
    gt_record: Optional[Dict[str, Any]],
    dense_candidates: List[RetrievedChunk],
    reranked_chunks: List[RetrievedChunk],
    top_k: int = 5,
) -> None:
    """Analyze ground-truth retrieval status before and after reranking."""
    if not gt_record:
        print("\n" + "=" * 100)
        print("GROUND-TRUTH RELEVANCE & RETRIEVAL EVALUATION")
        print("=" * 100)
        print("Note: This query has no ground-truth benchmark entry. Skipping labeled accuracy metrics.")
        print("-" * 100)
        return

    rel_chunks: List[str] = gt_record.get("relevant_chunks", [])
    rationale = gt_record.get("rationale", "")
    eligible = gt_record.get("evaluation_eligible", True)

    cand_top20_ids = [c.chunk_id for c in dense_candidates]
    dense_top5_ids = [c.chunk_id for c in dense_candidates[:top_k]]
    rerank_top5_ids = [c.chunk_id for c in reranked_chunks[:top_k]]

    # Candidate presence
    cand_hits = [cid for cid in rel_chunks if cid in cand_top20_ids]
    cand_hit_ranks = [cand_top20_ids.index(cid) + 1 for cid in cand_hits]

    # Dense Top-5 presence
    dense_first_rank = next((idx for idx, cid in enumerate(dense_top5_ids, start=1) if cid in rel_chunks), None)
    dense_hit = dense_first_rank is not None

    # Reranked Top-5 presence
    rerank_first_rank = next((idx for idx, cid in enumerate(rerank_top5_ids, start=1) if cid in rel_chunks), None)
    rerank_hit = rerank_first_rank is not None

    # Classification
    if not dense_hit and rerank_hit:
        impact = "IMPROVED (Dense Miss -> BGE Hit)"
        verdict_icon = "✅"
    elif dense_hit and not rerank_hit:
        impact = "REGRESSED (Dense Hit -> BGE Miss)"
        verdict_icon = "❌"
    elif dense_hit and rerank_hit:
        impact = f"MAINTAINED HIT (Dense Rank {dense_first_rank} -> BGE Rank {rerank_first_rank})"
        verdict_icon = "✅"
    else:
        impact = "UNCHANGED (Miss in both pipelines)"
        verdict_icon = "⚠️"

    print("\n" + "=" * 100)
    print("GROUND-TRUTH RELEVANCE & RETRIEVAL EVALUATION")
    print("=" * 100)
    print(f"Benchmark Question ID   : {question_id}")
    print(f"Evaluation Eligible     : {eligible}")
    print(f"Expected Relevant Chunks: {rel_chunks} ({len(rel_chunks)} chunks)")
    if rationale:
        print(f"Relevance Rationale     : {rationale}")
    print("-" * 100)

    print(f"1. Candidate Recall @ 20 : {'YES' if cand_hits else 'NO'}")
    if cand_hits:
        hits_desc = ", ".join([f"{cid} (Dense Rank [{r}])" for cid, r in zip(cand_hits, cand_hit_ranks)])
        print(f"   Found {len(cand_hits)}/{len(rel_chunks)} relevant chunks in Top 20: {hits_desc}")
    else:
        print("   ❌ ZERO relevant chunks were retrieved in the Top 20 candidate pool.")
        print("      (Root cause: Candidate Recall failure. Reranker cannot rescue this query.)")

    print(f"\n2. Dense Baseline Top-{top_k}  : {'YES (HIT at Rank ' + str(dense_first_rank) + ')' if dense_hit else 'NO (MISS)'}")
    print(f"3. BGE Reranked Top-{top_k}    : {'YES (HIT at Rank ' + str(rerank_first_rank) + ')' if rerank_hit else 'NO (MISS)'}")

    print(f"\n4. Pipeline Impact       : {verdict_icon} {impact}")

    # Concrete explanation
    print("\nDetailed Analysis:")
    if not cand_hits:
        print(
            "  * Candidate pool limitation: Dense retrieval failed to include any relevant chunk in the Top 20.\n"
            "    Because cross-encoders only re-order existing candidates, reranking cannot resolve this miss.\n"
            "    Resolution requires hybrid search (BM25) or improved query embeddings."
        )
    elif not dense_hit and rerank_hit:
        best_cand_cid = next(cid for cid in rerank_top5_ids if cid in rel_chunks)
        best_d_rank = dense_candidates.index(next(c for c in dense_candidates if c.chunk_id == best_cand_cid)) + 1
        print(
            f"  * Cross-encoder victory: Relevant chunk '{best_cand_cid}' was originally at Dense Rank [{best_d_rank}]\n"
            f"    (outside Top-{top_k}). BGE Reranker recognized its high semantic alignment and promoted it to Rank [{rerank_first_rank}],\n"
            f"    successfully converting a retrieval miss into an accurate Hit@{top_k}!"
        )
    elif dense_hit and not rerank_hit:
        demoted_cid = next(cid for cid in dense_top5_ids if cid in rel_chunks)
        new_rank = next((idx for idx, c in enumerate(reranked_chunks, start=1) if c.chunk_id == demoted_cid), None)
        print(
            f"  * Cross-encoder regression: Relevant chunk '{demoted_cid}' was present at Dense Rank [{dense_first_rank}],\n"
            f"    but was demoted by the reranker to Rank [{new_rank}] because alternative/procedural passages\n"
            f"    received higher cross-encoder relevance scores."
        )
    elif dense_hit and rerank_hit:
        if rerank_first_rank < dense_first_rank:
            print(
                f"  * Rank improvement: Relevant chunk promoted from Rank [{dense_first_rank}] to Rank [{rerank_first_rank}],\n"
                f"    improving Reciprocal Rank (MRR: {1.0/dense_first_rank:.4f} -> {1.0/rerank_first_rank:.4f})."
            )
        elif rerank_first_rank > dense_first_rank:
            print(
                f"  * Rank preserved in Top-{top_k}: Relevant chunk shifted from Rank [{dense_first_rank}] to Rank [{rerank_first_rank}],\n"
                f"    maintaining Hit@{top_k} success."
            )
        else:
            print(f"  * Stable: Relevant chunk remained at Rank [{rerank_first_rank}].")
    else:
        print(
            "  * Persistent miss: Relevant chunk was present in candidates (Rank "
            f"{cand_hit_ranks[0] if cand_hit_ranks else '?'}), but neither retriever nor reranker placed it into Top-{top_k}."
        )

    print("-" * 100)


# =========================================================================
# CPU CONFIRMATION PROMPT
# =========================================================================

def confirm_reranking(num_candidates: int, auto_yes: bool = False) -> bool:
    """Warn user about CPU inference duration and prompt for confirmation."""
    if auto_yes:
        return True

    print("\n" + "-" * 100)
    print("⚠️  CPU INFERENCE WARNING:")
    print(f"   Reranking {num_candidates} candidate chunks with '{RERANKER_MODEL}' (568M params) on CPU")
    print(f"   takes approximately 60 to 90 seconds (single query inference).")
    print("-" * 100)

    try:
        choice = input("Proceed with BGE reranking inference? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            return True
        print("\nOperation cancelled. Showing dense retrieval candidates only.")
        return False
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled by user.")
        return False


# =========================================================================
# MAIN DIAGNOSTIC WORKFLOW
# =========================================================================

def run_diagnostic_for_query(
    user_input: str,
    gt_dict: Dict[str, Any],
    questions_dict: Dict[str, str],
    reranker: Optional[CrossEncoderReranker],
    auto_yes: bool = False,
    top_candidates: int = DEFAULT_TOP_CANDIDATES,
    top_final: int = DEFAULT_TOP_FINAL,
) -> Optional[CrossEncoderReranker]:
    """Execute complete 2-stage retrieval and reranking diagnostic for a single query."""
    query_text, question_id, gt_record = resolve_query(user_input, gt_dict, questions_dict)

    print("\n" + "=" * 100)
    print("CYBERSECURITY RAG — BGE RERANKER INSPECTION & DIAGNOSTIC")
    print("=" * 100)
    if question_id:
        print(f"Evaluation Question ID : {question_id}")
    print(f"Target Query Text      : \"{query_text}\"")
    rel_chunks = gt_record.get("relevant_chunks", []) if gt_record else []
    if rel_chunks:
        print(f"Ground-Truth Chunks    : {', '.join(rel_chunks)}")
    print("=" * 100)

    # ---------------------------------------------------------------------
    # Stage 1: Dense Retrieval
    # ---------------------------------------------------------------------
    print("\n[Stage 1/2] Executing Dense Semantic Retrieval (BAAI/bge-m3 via Qdrant)...")
    t0 = time.perf_counter()
    with DenseRetriever(
        embedding_model_name=EMBEDDING_MODEL,
        collection_name=COLLECTION_NAME,
    ) as retriever:
        dense_candidates = retriever.retrieve(query_text, top_k=top_candidates)
    dense_latency_ms = (time.perf_counter() - t0) * 1000

    if not dense_candidates:
        print("❌ ERROR: No candidate chunks were returned from dense retrieval.")
        return reranker

    # Record dense ranks map
    dense_ranks = {c.chunk_id: idx for idx, c in enumerate(dense_candidates, start=1)}

    # Display Stage 1 Results
    display_candidates(
        dense_candidates,
        relevant_chunks=rel_chunks,
        title=f"STAGE 1: DENSE RETRIEVAL TOP {len(dense_candidates)} CANDIDATES",
        query=query_text,
        latency_ms=dense_latency_ms,
    )

    # ---------------------------------------------------------------------
    # CPU Warning & Confirmation
    # ---------------------------------------------------------------------
    should_proceed = confirm_reranking(len(dense_candidates), auto_yes=auto_yes)
    if not should_proceed:
        return reranker

    # ---------------------------------------------------------------------
    # Stage 2: BGE Cross-Encoder Reranking
    # ---------------------------------------------------------------------
    print(f"\n[Stage 2/2] Loading & Scoring Candidates with '{RERANKER_MODEL}' on CPU...")
    if reranker is None:
        t_load0 = time.perf_counter()
        reranker = CrossEncoderReranker(model_name=RERANKER_MODEL, lazy_load=False)
        t_load = time.perf_counter() - t_load0
        print(f"  Model loaded into memory in {t_load:.2f} s")
    else:
        print("  Reusing preloaded BGE Reranker model instance.")

    t_rerank0 = time.perf_counter()
    # Pass exact same candidate pool to reranker
    reranked = reranker.rerank(query_text, dense_candidates, top_n=top_candidates)
    rerank_latency_s = time.perf_counter() - t_rerank0

    # ---------------------------------------------------------------------
    # Stage 3: Display Detailed Analysis & Comparisons
    # ---------------------------------------------------------------------
    # 1. Full 20-candidate reranked table with rank movements
    display_reranked_table(
        reranked,
        dense_ranks=dense_ranks,
        relevant_chunks=rel_chunks,
        latency_s=rerank_latency_s,
    )

    # 2. Final Reranked Top 5
    display_final_top5(
        reranked,
        dense_ranks=dense_ranks,
        relevant_chunks=rel_chunks,
        top_k=top_final,
    )

    # 3. Dense Top-5 vs Reranked Top-5 composition comparison
    display_composition_comparison(
        dense_candidates,
        reranked,
        dense_ranks=dense_ranks,
        relevant_chunks=rel_chunks,
        top_k=top_final,
    )

    # 4. Ground-truth relevance evaluation & root cause explanation
    display_ground_truth_analysis(
        question_id=question_id,
        gt_record=gt_record,
        dense_candidates=dense_candidates,
        reranked_chunks=reranked,
        top_k=top_final,
    )

    return reranker


def main():
    parser = argparse.ArgumentParser(
        description="Inspect Dense Retrieval and BGE-Reranker v2-m3 Pipeline step-by-step."
    )
    parser.add_argument(
        "-q", "--question-id",
        type=str,
        default=None,
        help="Evaluation question ID (e.g. Q10, Q13, Q8, Q30, Q36).",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Custom query string to retrieve and rerank.",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the CPU inference confirmation prompt and proceed immediately.",
    )
    parser.add_argument(
        "--top-candidates",
        type=int,
        default=DEFAULT_TOP_CANDIDATES,
        help=f"Number of dense candidates to retrieve (default: {DEFAULT_TOP_CANDIDATES}).",
    )
    parser.add_argument(
        "--top-final",
        type=int,
        default=DEFAULT_TOP_FINAL,
        help=f"Number of final reranked chunks to display in Top-N (default: {DEFAULT_TOP_FINAL}).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Stay in an interactive loop after the first query to inspect more questions.",
    )
    args = parser.parse_args()

    gt_dict, questions_dict = load_ground_truth_data()
    reranker_instance: Optional[CrossEncoderReranker] = None

    # Determine initial target
    initial_target = args.question_id or args.query

    if initial_target:
        reranker_instance = run_diagnostic_for_query(
            initial_target,
            gt_dict=gt_dict,
            questions_dict=questions_dict,
            reranker=reranker_instance,
            auto_yes=args.yes,
            top_candidates=args.top_candidates,
            top_final=args.top_final,
        )

        if not args.loop:
            if reranker_instance is not None:
                reranker_instance.close()
            return

    # Interactive Loop Mode
    print("\n" + "=" * 100)
    print("INTERACTIVE BGE RERANKING INSPECTION MODE")
    print("=" * 100)
    print("Available options: Enter a Question ID (e.g. Q10, Q13, Q8), a custom query, or 'exit' to quit.\n")

    try:
        while True:
            prompt_text = "Enter Question ID or query [or 'exit']: "
            user_input = input(prompt_text).strip()

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting diagnostic.")
                break

            reranker_instance = run_diagnostic_for_query(
                user_input,
                gt_dict=gt_dict,
                questions_dict=questions_dict,
                reranker=reranker_instance,
                auto_yes=args.yes,
                top_candidates=args.top_candidates,
                top_final=args.top_final,
            )

    except (KeyboardInterrupt, EOFError):
        print("\nDiagnostic session terminated.")
    finally:
        if reranker_instance is not None:
            reranker_instance.close()


if __name__ == "__main__":
    main()
