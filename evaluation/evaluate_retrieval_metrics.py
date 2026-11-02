import sys
import time
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Windows console UTF-8 fix for special symbols in chunk texts
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from app.core.models import ChunkMetadata, RetrievedChunk
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.confidence import ConfidenceEvaluator, merge_candidate_pools
from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.rrf import RRFFusion
from app.retrieval.reranker import CrossEncoderReranker, combine_candidate_pools


# ============================================================
# CONFIG
# ============================================================

QDRANT_PATH = str(PROJECT_ROOT / "data" / "qdrant")

COLLECTION_NAME = "cybersecurity_chunks_bge_m3"

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

VECTOR_DIMENSION = 1024

TOP_K = 5

QUESTIONS_FILE = PROJECT_ROOT / "data" / "evaluation" / "evaluation_questions.json"

BASELINE_GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_current.json"

ADDITIONAL_GROUND_TRUTH_FILE = PROJECT_ROOT / "data" / "evaluation" / "retrieval_ground_truth_additional_20.json"

SIX_DENSE_MISSES = ["Q10", "Q13", "Q19", "Q25", "Q36", "Q38"]


# ============================================================
# LOAD GROUND TRUTH
# ============================================================

def load_ground_truth(eval_set: str = "baseline") -> Tuple[Dict[str, Any], int, str]:
    """Load retrieval ground-truth dataset based on eval_set selection.

    Returns:
        ground_truth: Dictionary of ground-truth entries.
        expected_count: Expected number of evaluation-eligible questions.
        eval_label: Descriptive label of the evaluation set.
    """
    if eval_set == "baseline":
        if not BASELINE_GROUND_TRUTH_FILE.exists():
            print(f"❌ ERROR: Baseline ground-truth file not found: {BASELINE_GROUND_TRUTH_FILE}")
            sys.exit(1)
        with open(BASELINE_GROUND_TRUTH_FILE, "r", encoding="utf-8") as file:
            return json.load(file), 15, "Baseline (15 Questions: Q1-Q13, Q16, Q17, Q19, Q20)"

    elif eval_set == "additional":
        if not ADDITIONAL_GROUND_TRUTH_FILE.exists():
            print(f"❌ ERROR: Additional ground-truth file not found: {ADDITIONAL_GROUND_TRUTH_FILE}")
            sys.exit(1)
        with open(ADDITIONAL_GROUND_TRUTH_FILE, "r", encoding="utf-8") as file:
            return json.load(file), 20, "Additional (20 Questions: Q21-Q40 across 20 Publications)"

    elif eval_set in ("all", "combined"):
        if not BASELINE_GROUND_TRUTH_FILE.exists():
            print(f"❌ ERROR: Baseline ground-truth file not found: {BASELINE_GROUND_TRUTH_FILE}")
            sys.exit(1)
        if not ADDITIONAL_GROUND_TRUTH_FILE.exists():
            print(f"❌ ERROR: Additional ground-truth file not found: {ADDITIONAL_GROUND_TRUTH_FILE}")
            sys.exit(1)
        with open(BASELINE_GROUND_TRUTH_FILE, "r", encoding="utf-8") as f1, \
             open(ADDITIONAL_GROUND_TRUTH_FILE, "r", encoding="utf-8") as f2:
            gt1 = json.load(f1)
            gt2 = json.load(f2)
            merged = {**gt1, **gt2}
            return merged, 35, "Combined Full Evaluation (35 Questions: 15 Baseline + 20 Additional)"

    else:
        print(f"❌ ERROR: Unknown eval_set '{eval_set}'. Choose from 'baseline', 'additional', or 'all'.")
        sys.exit(1)


# ============================================================
# LOAD ELIGIBLE QUESTIONS
# ============================================================

def load_eligible_questions(ground_truth: Dict[str, Any], expected_count: int) -> List[Dict[str, Any]]:
    """Load and filter questions where evaluation_eligible is True in ground truth."""
    if not Path(QUESTIONS_FILE).exists():
        print(f"❌ ERROR: Questions file not found: {QUESTIONS_FILE}")
        sys.exit(1)

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as file:
        all_questions = json.load(file)

    eligible_questions = []
    for item in all_questions:
        q_id = item.get("id")
        gt_entry = ground_truth.get(q_id, {})
        if gt_entry.get("evaluation_eligible") is True:
            eligible_questions.append(item)

    if len(eligible_questions) != expected_count:
        print(
            f"❌ ERROR: Expected {expected_count} evaluation-eligible questions, "
            f"but found {len(eligible_questions)}."
        )
        print(f"Found Question IDs: {[q.get('id') for q in eligible_questions]}")
        sys.exit(1)

    return eligible_questions


# ============================================================
# LOAD EMBEDDING MODEL
# ============================================================

def load_embedding_model() -> SentenceTransformer:
    """Load BGE-M3 using local cache files only."""
    print(f"\nLoading {EMBEDDING_MODEL_NAME} from local cache...")
    try:
        model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            local_files_only=True
        )
        print(f"✅ {EMBEDDING_MODEL_NAME} loaded from local cache")
        return model
    except Exception as exc:
        print(
            f"\n❌ ERROR: Failed to load '{EMBEDDING_MODEL_NAME}' from local cache: {exc}\n"
            f"Please verify model files are present in the Hugging Face cache."
        )
        sys.exit(1)


# ============================================================
# VALIDATE COLLECTION & VECTOR DIMENSIONS
# ============================================================

def validate_collection_and_dimensions(client: QdrantClient, model: SentenceTransformer) -> None:
    """Verify collection exists, matches expected vector dimension, and model dimension matches."""
    print(f"\nVerifying Qdrant collection '{COLLECTION_NAME}'...")

    try:
        collection_info = client.get_collection(collection_name=COLLECTION_NAME)
    except Exception as exc:
        print(
            f"\n❌ ERROR: Could not access Qdrant collection '{COLLECTION_NAME}': {exc}"
        )
        sys.exit(1)

    vectors_config = collection_info.config.params.vectors

    collection_dim = (
        vectors_config.size
        if hasattr(vectors_config, "size")
        else getattr(vectors_config, "get", lambda k: None)("size")
    )

    distance_metric = (
        vectors_config.distance
        if hasattr(vectors_config, "distance")
        else getattr(vectors_config, "get", lambda k: None)("distance")
    )

    print(f"  Collection Name  : {COLLECTION_NAME}")
    print(f"  Vectors Count    : {collection_info.points_count:,}")
    print(f"  Vector Dimension : {collection_dim}")
    print(f"  Distance Metric  : {distance_metric}")

    if collection_dim != VECTOR_DIMENSION:
        print(
            f"\n❌ ERROR: Collection vector dimension ({collection_dim}) does not match "
            f"expected dimension ({VECTOR_DIMENSION})."
        )
        sys.exit(1)

    # Validate embedding model dimension
    model_dim = model.get_sentence_embedding_dimension()
    if model_dim != VECTOR_DIMENSION:
        print(
            f"\n❌ ERROR: Model embedding dimension ({model_dim}) does not match "
            f"expected dimension ({VECTOR_DIMENSION})."
        )
        sys.exit(1)

    print("✅ Collection and embedding model vector dimensions match perfectly (1024).")


# ============================================================
# VALIDATE RELEVANT CHUNK IDS IN QDRANT
# ============================================================

def validate_relevant_chunk_ids(client: QdrantClient, questions: List[Dict[str, Any]], ground_truth: Dict[str, Any]) -> None:
    """Verify every relevant chunk ID for eligible questions exists in Qdrant."""
    required_chunk_ids = set()
    for q in questions:
        q_id = q["id"]
        gt_entry = ground_truth.get(q_id, {})
        for cid in gt_entry.get("relevant_chunks", []):
            required_chunk_ids.add(cid)

    print(
        f"\nValidating {len(required_chunk_ids)} unique relevant chunk IDs in collection..."
    )

    existing_chunk_ids = set()
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1000,
            offset=offset,
            with_payload=["chunk_id"],
            with_vectors=False,
        )
        for pt in points:
            if pt.payload and "chunk_id" in pt.payload:
                existing_chunk_ids.add(pt.payload["chunk_id"])

        if next_offset is None:
            break
        offset = next_offset

    missing_chunk_ids = sorted(list(required_chunk_ids - existing_chunk_ids))

    if missing_chunk_ids:
        print(
            f"\n❌ ERROR: {len(missing_chunk_ids)} relevant chunk IDs from ground truth "
            f"are missing from Qdrant collection '{COLLECTION_NAME}':"
        )
        for mcid in missing_chunk_ids:
            print(f"  - {mcid}")
        sys.exit(1)

    print(
        f"✅ All {len(required_chunk_ids)} relevant chunk IDs confirmed present in Qdrant collection."
    )


# ============================================================
# RETRIEVAL HELPERS
# ============================================================

def retrieve_dense(
    client: QdrantClient,
    model: SentenceTransformer,
    question: str,
    limit: int = TOP_K
) -> List[RetrievedChunk]:
    """Generate query embedding and retrieve candidate chunks from Qdrant."""
    query_vector = model.encode(
        question,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    if query_vector.shape[0] != VECTOR_DIMENSION:
        raise ValueError(
            f"Query embedding dimension ({query_vector.shape[0]}) does not match "
            f"expected dimension ({VECTOR_DIMENSION})."
        )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector.tolist(),
        limit=limit,
        with_payload=True
    ).points

    candidates: List[RetrievedChunk] = []
    for pt in results:
        payload = pt.payload or {}
        chunk_id = payload.get("chunk_id")
        if not chunk_id:
            continue
        candidates.append(
            RetrievedChunk(
                chunk_id=str(chunk_id),
                text=str(payload.get("text", "")),
                score=float(pt.score),
                dense_score=float(pt.score),
                metadata=ChunkMetadata.from_dict(payload),
            )
        )
    return candidates


def retrieve_documents(client: QdrantClient, model: SentenceTransformer, question: str, top_k: int = TOP_K):
    """Backwards-compatible interface returning raw Qdrant points."""
    query_vector = model.encode(
        question,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    if query_vector.shape[0] != VECTOR_DIMENSION:
        raise ValueError(
            f"Query embedding dimension ({query_vector.shape[0]}) does not match "
            f"expected dimension ({VECTOR_DIMENSION})."
        )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector.tolist(),
        limit=top_k,
        with_payload=True
    ).points

    return results


def get_chunk_ids(results) -> List[str]:
    """Extract chunk_id strings from retrieval result list."""
    chunk_ids = []
    for result in results:
        if isinstance(result, RetrievedChunk):
            chunk_ids.append(result.chunk_id)
        elif hasattr(result, "payload") and result.payload:
            cid = result.payload.get("chunk_id")
            if cid:
                chunk_ids.append(str(cid))
        elif isinstance(result, dict):
            cid = result.get("chunk_id") or result.get("id")
            if cid:
                chunk_ids.append(str(cid))
    return chunk_ids


def retrieve_bm25(bm25_retriever: BM25Retriever, question: str, limit: int = TOP_K) -> List[RetrievedChunk]:
    """Retrieve top candidate chunks using BM25 keyword matching."""
    return bm25_retriever.retrieve(question, top_k=limit)


def retrieve_hybrid(
    client: QdrantClient,
    model: SentenceTransformer,
    bm25_retriever: BM25Retriever,
    fusion: RRFFusion,
    question: str,
    dense_limit: int = 25,
    bm25_limit: int = 25,
    top_k: int = TOP_K,
) -> Tuple[List[RetrievedChunk], List[RetrievedChunk], List[RetrievedChunk]]:
    """Execute hybrid retrieval combining dense semantic candidates and BM25 candidates via RRF."""
    dense_candidates = retrieve_dense(client, model, question, limit=dense_limit)
    bm25_candidates = retrieve_bm25(bm25_retriever, question, limit=bm25_limit)
    fused_results = fusion.fuse([dense_candidates, bm25_candidates], top_k=top_k)
    return fused_results, dense_candidates, bm25_candidates


# ============================================================
# METRICS COMPUTATION
# ============================================================

def calculate_hit_at_k(retrieved_chunks: Sequence[str], relevant_chunks: Sequence[str], k: int) -> int:
    """Return 1 if at least one relevant chunk is in the top-k retrieved chunks, else 0."""
    retrieved_top_k = retrieved_chunks[:k]
    for chunk_id in retrieved_top_k:
        if chunk_id in relevant_chunks:
            return 1
    return 0


def calculate_precision_at_k(retrieved_chunks: Sequence[str], relevant_chunks: Sequence[str], k: int) -> float:
    """Calculate Precision@k: relevant chunks in top-k divided by k."""
    retrieved_top_k = retrieved_chunks[:k]
    if not retrieved_top_k:
        return 0.0
    relevant_count = sum(1 for cid in retrieved_top_k if cid in relevant_chunks)
    return relevant_count / len(retrieved_top_k)


def calculate_recall_at_k(retrieved_chunks: Sequence[str], relevant_chunks: Sequence[str], k: int) -> float:
    """Calculate Recall@k: relevant chunks in top-k divided by total relevant chunks."""
    if not relevant_chunks:
        return 0.0
    retrieved_top_k = retrieved_chunks[:k]
    relevant_count = sum(1 for cid in retrieved_top_k if cid in relevant_chunks)
    return relevant_count / len(relevant_chunks)


def calculate_mrr(retrieved_chunks: Sequence[str], relevant_chunks: Sequence[str]) -> float:
    """Calculate Reciprocal Rank (1/rank) of first relevant chunk, or 0.0 if not found."""
    for rank, chunk_id in enumerate(retrieved_chunks, start=1):
        if chunk_id in relevant_chunks:
            return 1.0 / rank
    return 0.0


def compute_metrics(retrieved_chunks: Sequence[str], relevant_chunks: Sequence[str], k: int = TOP_K) -> Dict[str, float]:
    """Compute all standard evaluation metrics for a single question."""
    return {
        "hit@1": float(calculate_hit_at_k(retrieved_chunks, relevant_chunks, 1)),
        "hit@3": float(calculate_hit_at_k(retrieved_chunks, relevant_chunks, 3)),
        "hit@5": float(calculate_hit_at_k(retrieved_chunks, relevant_chunks, k)),
        "hit@10": float(calculate_hit_at_k(retrieved_chunks, relevant_chunks, 10)),
        "hit@20": float(calculate_hit_at_k(retrieved_chunks, relevant_chunks, 20)),
        "precision@5": calculate_precision_at_k(retrieved_chunks, relevant_chunks, k),
        "recall@5": calculate_recall_at_k(retrieved_chunks, relevant_chunks, k),
        "mrr": calculate_mrr(retrieved_chunks, relevant_chunks),
    }


def macro_average(metric_dicts: List[Dict[str, float]]) -> Dict[str, float]:
    """Compute macro-averaged metrics across all evaluated questions."""
    count = len(metric_dicts)
    if count == 0:
        return {}
    keys = ["hit@1", "hit@3", "hit@5", "hit@10", "hit@20", "precision@5", "recall@5", "mrr"]
    return {k: sum(m[k] for m in metric_dicts) / count for k in keys}


# ============================================================
# CLI PARSER
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval and reranking metrics on Cybersecurity RAG."
    )
    parser.add_argument(
        "--eval-set",
        type=str,
        choices=["baseline", "additional", "all", "combined"],
        default="baseline",
        help="Evaluation set: 'baseline' (15 questions), 'additional' (20 questions), or 'all' (35 questions). Default: baseline.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["dense", "bm25", "hybrid", "rerank_dense", "rerank_hybrid", "adaptive", "compare"],
        default="dense",
        help="Retrieval mode: 'dense' (BGE-M3), 'bm25' (BM25Okapi), 'hybrid' (RRF), 'rerank_dense' (Dense+CrossEncoder), 'rerank_hybrid' (Dense+BM25+CrossEncoder), 'adaptive' (Adaptive Rewriting), or 'compare' (side-by-side). Default: dense.",
    )
    parser.add_argument(
        "--dense-candidates",
        type=int,
        default=25,
        help="Number of dense candidates to retrieve before fusion/reranking (default: 25).",
    )
    parser.add_argument(
        "--bm25-candidates",
        type=int,
        default=25,
        help="Number of BM25 candidates to retrieve before fusion/reranking (default: 25).",
    )
    parser.add_argument(
        "--dense-weight",
        type=float,
        default=0.8,
        help="Weight assigned to dense retriever in RRF fusion (default: 0.8).",
    )
    parser.add_argument(
        "--bm25-weight",
        type=float,
        default=0.2,
        help="Weight assigned to BM25 retriever in RRF fusion (default: 0.2).",
    )
    parser.add_argument(
        "--rrf-k",
        type=int,
        default=20,
        help="RRF smoothing constant k (default: 20).",
    )
    parser.add_argument(
        "--reranker-model",
        type=str,
        default=RERANKER_MODEL_NAME,
        help=f"Cross-Encoder reranker model name (default: {RERANKER_MODEL_NAME}).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of final evaluated chunks (default: 5).",
    )
    parser.add_argument(
        "--enable-query-rewriting",
        action="store_true",
        default=False,
        help="Enable LLM-based query rewriting before document retrieval.",
    )
    parser.add_argument(
        "--enable-adaptive-query-rewriting",
        action="store_true",
        default=False,
        help="Enable adaptive query rewriting triggered by low retrieval confidence.",
    )
    parser.add_argument(
        "--adaptive-confidence-threshold",
        type=float,
        default=0.735,
        help="Top-1 dense score threshold for adaptive rewriting confidence (default: 0.735).",
    )
    parser.add_argument(
        "--adaptive-confidence-mean-threshold",
        type=float,
        default=0.700,
        help="Top-3 mean dense score threshold for adaptive rewriting confidence (default: 0.700).",
    )
    parser.add_argument(
        "--query-rewriter-model",
        type=str,
        default=None,
        help="Model name for query rewriter (default: settings.query_rewriter_model).",
    )
    return parser.parse_args()


# ============================================================
# MAIN EVALUATION
# ============================================================

def main():
    args = parse_args()
    eval_set = "all" if args.eval_set == "combined" else args.eval_set
    mode = args.mode

    print("=" * 80)
    print(f"RAG RETRIEVAL & RERANKING EVALUATION — MODE: {mode.upper()}")
    print("=" * 80)

    # 1. Load ground truth and eligible questions
    ground_truth, expected_count, eval_label = load_ground_truth(eval_set)
    questions = load_eligible_questions(ground_truth, expected_count)

    print(f"\nEvaluation Set   : {eval_label}")
    print(f"Total in Ground  : {len(ground_truth)} questions")
    print(
        f"Eligible Selected: {len(questions)} questions ("
        f"{', '.join([q['id'] for q in questions])})"
    )

    client: Optional[QdrantClient] = None
    model: Optional[SentenceTransformer] = None
    bm25_retriever: Optional[BM25Retriever] = None
    fusion: Optional[RRFFusion] = None
    reranker: Optional[CrossEncoderReranker] = None

    try:
        # 2. Initialize required components based on mode
        need_dense = mode in ("dense", "hybrid", "rerank_dense", "rerank_hybrid", "adaptive", "compare")
        need_bm25 = mode in ("bm25", "hybrid", "rerank_hybrid", "compare")
        need_reranker = mode in ("rerank_dense", "rerank_hybrid") or (mode == "compare" and not args.enable_adaptive_query_rewriting)

        if need_dense:
            model = load_embedding_model()
            print("\nConnecting to Qdrant...")
            client = QdrantClient(path=QDRANT_PATH)
            print("✅ Qdrant connected")
            validate_collection_and_dimensions(client, model)
            validate_relevant_chunk_ids(client, questions, ground_truth)

        if need_bm25:
            print("\nInitializing BM25 index over authoritative chunks...")
            bm25_retriever = BM25Retriever(lazy_load=False)
            print(f"✅ BM25 index ready ({len(bm25_retriever.documents):,} chunks indexed)")

        if mode in ("hybrid", "compare"):
            weights = [args.dense_weight, args.bm25_weight]
            fusion = RRFFusion(k=args.rrf_k, weights=weights)
            print(f"✅ RRFFusion initialized with k={args.rrf_k}, weights (Dense: {args.dense_weight}, BM25: {args.bm25_weight})")

        if need_reranker:
            print(f"\nInitializing CrossEncoder reranker '{args.reranker_model}'...")
            reranker = CrossEncoderReranker(model_name=args.reranker_model, lazy_load=False)
            print(f"✅ CrossEncoder reranker loaded from local cache")

        query_rewriter: Optional[QueryRewriter] = None
        if args.enable_query_rewriting or args.enable_adaptive_query_rewriting or mode == "adaptive":
            query_rewriter = QueryRewriter(
                model_name=args.query_rewriter_model,
                enabled=True,
            )
            print(f"✅ Query rewriter initialized using model '{query_rewriter.model_name}'")

        confidence_evaluator = ConfidenceEvaluator(
            score_threshold=args.adaptive_confidence_threshold,
            mean_threshold=args.adaptive_confidence_mean_threshold,
        )

        print(f"\nStarting evaluation (Mode: {mode.upper()})...\n")

        rewriter_latencies = []
        fallback_count = 0

        # 3. Execution loops
        if mode == "compare":
            # --------------------------------------------------------
            # COMPARE MODE: 4-Way (if adaptive enabled) or 5-Way (standard)
            # --------------------------------------------------------
            if args.enable_adaptive_query_rewriting:
                strategies = [
                    "Dense Baseline",
                    "Always-On Rewrite",
                    "Adaptive Rewrite",
                    "Weighted RRF",
                ]
            else:
                strategies = [
                    "Dense Baseline",
                    "BM25 Alone",
                    "Weighted RRF",
                    "Dense + Reranker",
                    "Hybrid + Reranker",
                ]

            metrics_acc = {s: [] for s in strategies}
            coverage_acc = {s: 0 for s in strategies}
            latencies_acc = {s: [] for s in strategies}
            miss_tracking = {}

            adaptive_rewritten = 0
            adaptive_skipped = 0
            tp_adaptive = 0
            fp_adaptive = 0
            tn_adaptive = 0
            fn_adaptive = 0
            adaptive_rewrite_latencies = []

            for q_idx, q_item in enumerate(questions, start=1):
                q_id = q_item["id"]
                query_text = q_item["question"]
                q_gt = ground_truth.get(q_id, {})
                relevant_chunks = q_gt.get("relevant_chunks", [])

                print("-" * 80)
                print(f"[{q_idx}/{len(questions)}] {q_id}: {query_text[:75]}...")
                print(f"Relevant ({len(relevant_chunks)}): {', '.join(relevant_chunks)}")

                if args.enable_adaptive_query_rewriting:
                    # 1. Dense Baseline (Unmodified question)
                    t0 = time.perf_counter()
                    dense_base_cands = retrieve_dense(client, model, query_text, limit=args.dense_candidates)
                    t_dense_base = (time.perf_counter() - t0) * 1000
                    s1_top5 = [c.chunk_id for c in dense_base_cands[:args.top_k]]
                    m1 = compute_metrics([c.chunk_id for c in dense_base_cands], relevant_chunks, k=args.top_k)
                    metrics_acc["Dense Baseline"].append(m1)
                    coverage_acc["Dense Baseline"] += 1 if any(c.chunk_id in relevant_chunks for c in dense_base_cands[:args.top_k]) else 0
                    latencies_acc["Dense Baseline"].append(t_dense_base)

                    # 2. Always-On Rewrite
                    t_rw_0 = time.perf_counter()
                    rewr_res = query_rewriter.rewrite(query_text)
                    t_rw = (time.perf_counter() - t_rw_0) * 1000
                    rewriter_latencies.append(t_rw)
                    if rewr_res.fallback_used:
                        fallback_count += 1
                        print(f"  [Always-On Fallback] {rewr_res.error_message}")
                    else:
                        print(f"  [Rewriter ({t_rw:.1f}ms)] {rewr_res.rewritten_query[:75]}...")

                    search_query_always = (
                        rewr_res.rewritten_query
                        if (rewr_res.success and not rewr_res.fallback_used and rewr_res.rewritten_query)
                        else query_text
                    )
                    t0 = time.perf_counter()
                    always_cands = retrieve_dense(client, model, search_query_always, limit=args.dense_candidates)
                    t_always_dense = (time.perf_counter() - t0) * 1000
                    s2_top5 = [c.chunk_id for c in always_cands[:args.top_k]]
                    m2 = compute_metrics([c.chunk_id for c in always_cands], relevant_chunks, k=args.top_k)
                    metrics_acc["Always-On Rewrite"].append(m2)
                    coverage_acc["Always-On Rewrite"] += 1 if any(c.chunk_id in relevant_chunks for c in always_cands[:args.top_k]) else 0
                    latencies_acc["Always-On Rewrite"].append(t_always_dense + t_rw)

                    # 3. Adaptive Rewrite
                    conf_res = confidence_evaluator.evaluate(dense_base_cands)
                    hit_base = bool(m1["hit@5"])
                    if conf_res.is_confident:
                        adaptive_skipped += 1
                        if hit_base:
                            tn_adaptive += 1
                        else:
                            fn_adaptive += 1
                        adaptive_cands = dense_base_cands
                        t_adaptive = t_dense_base
                        print(f"  [Adaptive] CONFIDENT ({conf_res.reason}) — Skipped rewriter")
                    else:
                        adaptive_rewritten += 1
                        if hit_base:
                            fp_adaptive += 1
                        else:
                            tp_adaptive += 1
                        adaptive_rewrite_latencies.append(t_rw)
                        adaptive_cands = merge_candidate_pools(dense_base_cands, always_cands, limit=args.dense_candidates)
                        t_adaptive = t_dense_base + t_rw + t_always_dense
                        print(f"  [Adaptive] LOW CONFIDENCE ({conf_res.reason}) — Rewritten & Merged")

                    s3_top5 = [c.chunk_id for c in adaptive_cands[:args.top_k]]
                    m3 = compute_metrics([c.chunk_id for c in adaptive_cands], relevant_chunks, k=args.top_k)
                    metrics_acc["Adaptive Rewrite"].append(m3)
                    coverage_acc["Adaptive Rewrite"] += 1 if any(c.chunk_id in relevant_chunks for c in adaptive_cands[:args.top_k]) else 0
                    latencies_acc["Adaptive Rewrite"].append(t_adaptive)

                    # 4. Weighted RRF (Hybrid baseline using original query)
                    t0 = time.perf_counter()
                    bm25_base_cands = retrieve_bm25(bm25_retriever, query_text, limit=args.bm25_candidates)
                    t_bm25 = (time.perf_counter() - t0) * 1000
                    t0 = time.perf_counter()
                    fused = fusion.fuse([dense_base_cands, bm25_base_cands], top_k=max(20, args.top_k))
                    t_rrf = (time.perf_counter() - t0) * 1000
                    s4_top5 = [c.chunk_id for c in fused[:args.top_k]]
                    m4 = compute_metrics([c.chunk_id for c in fused], relevant_chunks, k=args.top_k)
                    metrics_acc["Weighted RRF"].append(m4)
                    pool_rrf_ids = {c.chunk_id for c in dense_base_cands} | {c.chunk_id for c in bm25_base_cands}
                    coverage_acc["Weighted RRF"] += 1 if any(cid in relevant_chunks for cid in pool_rrf_ids) else 0
                    latencies_acc["Weighted RRF"].append(t_dense_base + t_bm25 + t_rrf)

                    # Diagnostic print
                    print(f"  [1. Dense Base ] Hit@5: {'YES' if m1['hit@5'] else 'NO':<3} | MRR: {m1['mrr']:.4f} | Top: {s1_top5[0] if s1_top5 else 'None'}")
                    print(f"  [2. Always-On  ] Hit@5: {'YES' if m2['hit@5'] else 'NO':<3} | MRR: {m2['mrr']:.4f} | Top: {s2_top5[0] if s2_top5 else 'None'}")
                    print(f"  [3. Adaptive   ] Hit@5: {'YES' if m3['hit@5'] else 'NO':<3} | MRR: {m3['mrr']:.4f} | Top: {s3_top5[0] if s3_top5 else 'None'}")
                    print(f"  [4. Weight RRF ] Hit@5: {'YES' if m4['hit@5'] else 'NO':<3} | MRR: {m4['mrr']:.4f} | Top: {s4_top5[0] if s4_top5 else 'None'}")

                    # Track miss questions
                    if q_id in SIX_DENSE_MISSES:
                        def get_rank(cids):
                            return next((idx for idx, cid in enumerate(cids, start=1) if cid in relevant_chunks), None)

                        miss_tracking[q_id] = {
                            "relevant": relevant_chunks,
                            "s1_hit": bool(m1["hit@5"]),
                            "s2_hit": bool(m2["hit@5"]),
                            "s2_rank": get_rank([c.chunk_id for c in always_cands]),
                            "s3_hit": bool(m3["hit@5"]),
                            "s3_rank": get_rank([c.chunk_id for c in adaptive_cands]),
                            "s4_hit": bool(m4["hit@5"]),
                            "s4_rank": get_rank([c.chunk_id for c in fused]),
                        }

                else:
                    # Query rewriting if enabled
                    search_query = query_text
                    t_rewrite = 0.0
                    if query_rewriter is not None:
                        rewr_res = query_rewriter.rewrite(query_text)
                        search_query = rewr_res.rewritten_query
                        t_rewrite = rewr_res.latency_ms
                        rewriter_latencies.append(t_rewrite)
                        if rewr_res.fallback_used:
                            fallback_count += 1
                            print(f"  [Rewriter Fallback] {rewr_res.error_message}")
                        else:
                            print(f"  [Rewriter ({t_rewrite:.1f}ms)] {search_query[:75]}...")

                    # 1. Dense candidates
                    t0 = time.perf_counter()
                    dense_candidates = retrieve_dense(client, model, search_query, limit=args.dense_candidates)
                    t_dense = (time.perf_counter() - t0) * 1000

                    # 2. BM25 candidates
                    t0 = time.perf_counter()
                    bm25_candidates = retrieve_bm25(bm25_retriever, search_query, limit=args.bm25_candidates)
                    t_bm25 = (time.perf_counter() - t0) * 1000

                    # Strategy 1: Dense Baseline Top-5
                    s1_top5 = [c.chunk_id for c in dense_candidates[:args.top_k]]
                    m1 = compute_metrics([c.chunk_id for c in dense_candidates], relevant_chunks, k=args.top_k)
                    metrics_acc["Dense Baseline"].append(m1)
                    coverage_acc["Dense Baseline"] += 1 if any(c.chunk_id in relevant_chunks for c in dense_candidates[:args.top_k]) else 0
                    latencies_acc["Dense Baseline"].append(t_dense + t_rewrite)

                    # Strategy 2: BM25 Alone Top-5
                    s2_top5 = [c.chunk_id for c in bm25_candidates[:args.top_k]]
                    m2 = compute_metrics([c.chunk_id for c in bm25_candidates], relevant_chunks, k=args.top_k)
                    metrics_acc["BM25 Alone"].append(m2)
                    coverage_acc["BM25 Alone"] += 1 if any(c.chunk_id in relevant_chunks for c in bm25_candidates[:args.top_k]) else 0
                    latencies_acc["BM25 Alone"].append(t_bm25 + t_rewrite)

                    # Strategy 3: Weighted RRF Top-5
                    t0 = time.perf_counter()
                    fused = fusion.fuse([dense_candidates, bm25_candidates], top_k=max(20, args.top_k))
                    t_rrf = (time.perf_counter() - t0) * 1000
                    s3_top5 = [c.chunk_id for c in fused[:args.top_k]]
                    m3 = compute_metrics([c.chunk_id for c in fused], relevant_chunks, k=args.top_k)
                    metrics_acc["Weighted RRF"].append(m3)
                    pool_rrf_ids = {c.chunk_id for c in dense_candidates} | {c.chunk_id for c in bm25_candidates}
                    coverage_acc["Weighted RRF"] += 1 if any(cid in relevant_chunks for cid in pool_rrf_ids) else 0
                    latencies_acc["Weighted RRF"].append(t_dense + t_bm25 + t_rrf + t_rewrite)

                    # Strategy 4: Dense + Reranker Top-5
                    t0 = time.perf_counter()
                    s4_reranked = reranker.rerank(search_query, dense_candidates, top_n=max(20, args.top_k))
                    t_rerank_d = (time.perf_counter() - t0) * 1000
                    s4_top5 = [c.chunk_id for c in s4_reranked[:args.top_k]]
                    m4 = compute_metrics([c.chunk_id for c in s4_reranked], relevant_chunks, k=args.top_k)
                    metrics_acc["Dense + Reranker"].append(m4)
                    coverage_acc["Dense + Reranker"] += 1 if any(c.chunk_id in relevant_chunks for c in dense_candidates) else 0
                    latencies_acc["Dense + Reranker"].append(t_dense + t_rerank_d + t_rewrite)

                    # Strategy 5: Hybrid + Reranker Top-5
                    t0 = time.perf_counter()
                    hybrid_pool = combine_candidate_pools(dense_candidates, bm25_candidates)
                    s5_reranked = reranker.rerank(search_query, hybrid_pool, top_n=max(20, args.top_k))
                    t_rerank_h = (time.perf_counter() - t0) * 1000
                    s5_top5 = [c.chunk_id for c in s5_reranked[:args.top_k]]
                    m5 = compute_metrics([c.chunk_id for c in s5_reranked], relevant_chunks, k=args.top_k)
                    metrics_acc["Hybrid + Reranker"].append(m5)
                    coverage_acc["Hybrid + Reranker"] += 1 if any(c.chunk_id in relevant_chunks for c in hybrid_pool) else 0
                    latencies_acc["Hybrid + Reranker"].append(t_dense + t_bm25 + t_rerank_h + t_rewrite)

                    # Diagnostic print
                    print(f"  [1. Dense Base ] Hit@5: {'YES' if m1['hit@5'] else 'NO':<3} | MRR: {m1['mrr']:.4f} | Top: {s1_top5[0] if s1_top5 else 'None'}")
                    print(f"  [2. BM25 Alone ] Hit@5: {'YES' if m2['hit@5'] else 'NO':<3} | MRR: {m2['mrr']:.4f} | Top: {s2_top5[0] if s2_top5 else 'None'}")
                    print(f"  [3. Weight RRF ] Hit@5: {'YES' if m3['hit@5'] else 'NO':<3} | MRR: {m3['mrr']:.4f} | Top: {s3_top5[0] if s3_top5 else 'None'}")
                    print(f"  [4. Dense + RR ] Hit@5: {'YES' if m4['hit@5'] else 'NO':<3} | MRR: {m4['mrr']:.4f} | Top: {s4_top5[0] if s4_top5 else 'None'}")
                    print(f"  [5. Hybrid + RR] Hit@5: {'YES' if m5['hit@5'] else 'NO':<3} | MRR: {m5['mrr']:.4f} | Top: {s5_top5[0] if s5_top5 else 'None'}")

                    # Track miss questions
                    if q_id in SIX_DENSE_MISSES:
                        def get_rank(cids):
                            return next((idx for idx, cid in enumerate(cids, start=1) if cid in relevant_chunks), None)

                        miss_tracking[q_id] = {
                            "relevant": relevant_chunks,
                            "d_rank": get_rank([c.chunk_id for c in dense_candidates]),
                            "b_rank": get_rank([c.chunk_id for c in bm25_candidates]),
                            "s1_hit": bool(m1["hit@5"]),
                            "s3_hit": bool(m3["hit@5"]),
                            "s3_rank": get_rank(s3_top5),
                            "s4_hit": bool(m4["hit@5"]),
                            "s4_rank": get_rank(s4_top5),
                            "s5_hit": bool(m5["hit@5"]),
                            "s5_rank": get_rank(s5_top5),
                        }

            # Summary tables
            summaries = {s: macro_average(metrics_acc[s]) for s in strategies}
            avg_latencies = {s: sum(latencies_acc[s]) / len(latencies_acc[s]) for s in strategies}
            cov_rates = {s: coverage_acc[s] / len(questions) for s in strategies}

            print("\n" + "=" * 105)
            print("COMPARATIVE RETRIEVAL & RERANKING METRICS SUMMARY")
            print("=" * 105)
            print(f"Evaluation Set   : {eval_label}")
            print(f"Questions Tested : {len(questions)}")
            print(f"Candidate Limits : Dense={args.dense_candidates}, BM25={args.bm25_candidates} | RRF k={args.rrf_k}, w_d={args.dense_weight}, w_b={args.bm25_weight}")
            print("-" * 125)
            print(f"{'Strategy':<20} {'Coverage':>9} | {'Hit@1':>7} {'Hit@3':>7} {'Hit@5':>7} {'Hit@10':>7} {'Hit@20':>7} {'P@5':>7} {'R@5':>7} {'MRR':>8} | {'Avg Latency':>12}")
            print("-" * 125)

            for s in strategies:
                sum_m = summaries[s]
                cov_str = f"{cov_rates[s]:.1%}"
                lat_str = f"{avg_latencies[s]:.1f} ms"
                print(f"{s:<20} {cov_str:>9} | {sum_m['hit@1']:>6.2%} {sum_m['hit@3']:>6.2%} {sum_m['hit@5']:>6.2%} {sum_m['hit@10']:>6.2%} {sum_m['hit@20']:>6.2%} {sum_m['precision@5']:>6.2%} {sum_m['recall@5']:>6.2%} {sum_m['mrr']:>8.4f} | {lat_str:>12}")

            print("-" * 125)

            if args.enable_adaptive_query_rewriting:
                avg_rw_lat = sum(adaptive_rewrite_latencies) / len(adaptive_rewrite_latencies) if adaptive_rewrite_latencies else 0.0
                print(f"Adaptive Rewriting Statistics:")
                print(f"  Queries Rewritten       : {adaptive_rewritten}/{len(questions)} ({adaptive_rewritten / len(questions):.1%})")
                print(f"  Queries Kept Confident  : {adaptive_skipped}/{len(questions)} ({adaptive_skipped / len(questions):.1%})")
                print(f"  Rewrite Fallback Rate   : {fallback_count}/{len(questions)} ({fallback_count / len(questions):.1%})")
                print(f"  Avg Rewriter Latency    : {avg_rw_lat:.1f} ms / query (when triggered)")
                print(f"  True Positives (Rescued): {tp_adaptive}/6")
                print(f"  False Positives (R-Hits): {fp_adaptive}/29")
                print(f"  True Negatives (Kept)   : {tn_adaptive}/29")
                print(f"  False Negatives (Miss)  : {fn_adaptive}/6")

                print("\n" + "=" * 105)
                print("STATUS OF THE 6 DENSE BASELINE MISSES UNDER ALL STRATEGIES")
                print("=" * 105)
                print(f"{'Q_ID':<6} {'Dense Base':<14} {'Always-On':<16} {'Adaptive Rewrite':<20} {'Weighted RRF':<16}")
                print("-" * 105)
                for q_id in SIX_DENSE_MISSES:
                    if q_id in miss_tracking:
                        m = miss_tracking[q_id]
                        s1 = "YES" if m["s1_hit"] else "NO"
                        s2 = f"YES (R{m['s2_rank']})" if m["s2_hit"] else "NO"
                        s3 = f"YES (R{m['s3_rank']})" if m["s3_hit"] else "NO"
                        s4 = f"YES (R{m['s4_rank']})" if m["s4_hit"] else "NO"
                        print(f"{q_id:<6} {s1:<14} {s2:<16} {s3:<20} {s4:<16}")
                print("-" * 105)

            else:
                if query_rewriter is not None:
                    avg_rewr_lat = sum(rewriter_latencies) / len(rewriter_latencies) if rewriter_latencies else 0.0
                    print(f"Rewriter Latency : {avg_rewr_lat:.1f} ms / query (Fallbacks: {fallback_count}/{len(questions)})")

                # Print Detailed Miss Tracking
                print("\n" + "=" * 105)
                print("STATUS OF THE 6 DENSE BASELINE MISSES UNDER ALL STRATEGIES")
                print("=" * 105)
                print(f"{'Q_ID':<6} {'Dense Base':<12} {'Weighted RRF':<15} {'Dense + Reranker':<18} {'Hybrid + Reranker':<18}")
                print("-" * 105)
                for q_id in SIX_DENSE_MISSES:
                    if q_id in miss_tracking:
                        m = miss_tracking[q_id]
                        s1 = "NO" if not m["s1_hit"] else "YES"
                        s3 = f"YES (R{m['s3_rank']})" if m["s3_hit"] else "NO"
                        s4 = f"YES (R{m['s4_rank']})" if m["s4_hit"] else "NO"
                        s5 = f"YES (R{m['s5_rank']})" if m["s5_hit"] else "NO"
                        print(f"{q_id:<6} {s1:<12} {s3:<15} {s4:<18} {s5:<18}")
                print("-" * 105)

        else:
            # --------------------------------------------------------
            # SINGLE MODE: dense, bm25, hybrid, rerank_dense, or rerank_hybrid
            # --------------------------------------------------------
            metric_list = []
            latencies = []

            for question_item in questions:
                question_id = question_item["id"]
                question = question_item["question"]
                question_ground_truth = ground_truth.get(question_id, {})
                relevant_chunks = question_ground_truth.get("relevant_chunks", [])

                print("\n" + "=" * 70)
                print(f"{question_id}: {question}")
                print("=" * 70)

                # Query rewriting if enabled (for non-adaptive single modes)
                search_query = question
                t_rewrite = 0.0
                if query_rewriter is not None and mode != "adaptive":
                    rewr_res = query_rewriter.rewrite(question)
                    search_query = rewr_res.rewritten_query
                    t_rewrite = rewr_res.latency_ms
                    rewriter_latencies.append(t_rewrite)
                    if rewr_res.fallback_used:
                        fallback_count += 1
                        print(f"⚠️ Rewriter fallback used: {rewr_res.error_message}")
                    else:
                        print(f"🔄 Rewritten Query ({t_rewrite:.1f}ms): {search_query}")

                t0 = time.perf_counter()
                eval_depth = max(20, args.top_k)
                # Retrieve
                if mode == "dense":
                    dense_pts = retrieve_dense(client, model, search_query, limit=eval_depth)
                    retrieved_chunks = [c.chunk_id for c in dense_pts]
                elif mode == "bm25":
                    bm25_res = retrieve_bm25(bm25_retriever, search_query, limit=eval_depth)
                    retrieved_chunks = [c.chunk_id for c in bm25_res]
                elif mode == "hybrid":
                    fused_results, _, _ = retrieve_hybrid(
                        client, model, bm25_retriever, fusion, search_query,
                        dense_limit=args.dense_candidates,
                        bm25_limit=args.bm25_candidates,
                        top_k=eval_depth
                    )
                    retrieved_chunks = [c.chunk_id for c in fused_results]
                elif mode == "rerank_dense":
                    dense_cands = retrieve_dense(client, model, search_query, limit=args.dense_candidates)
                    reranked = reranker.rerank(search_query, dense_cands, top_n=eval_depth)
                    retrieved_chunks = [c.chunk_id for c in reranked]
                elif mode == "rerank_hybrid":
                    dense_cands = retrieve_dense(client, model, search_query, limit=args.dense_candidates)
                    bm25_cands = retrieve_bm25(bm25_retriever, search_query, limit=args.bm25_candidates)
                    pool = combine_candidate_pools(dense_cands, bm25_cands)
                    reranked = reranker.rerank(search_query, pool, top_n=eval_depth)
                    retrieved_chunks = [c.chunk_id for c in reranked]
                elif mode == "adaptive":
                    dense_pts = retrieve_dense(client, model, question, limit=eval_depth)
                    conf_res = confidence_evaluator.evaluate(dense_pts)
                    if conf_res.is_confident:
                        print(f"  [Adaptive] CONFIDENT ({conf_res.reason}) — Kept initial results")
                        retrieved_chunks = [c.chunk_id for c in dense_pts]
                    else:
                        print(f"  [Adaptive] LOW CONFIDENCE ({conf_res.reason}) — Triggering rewriter")
                        t_rw_0 = time.perf_counter()
                        rewr_res = query_rewriter.rewrite(question)
                        t_rewrite = (time.perf_counter() - t_rw_0) * 1000
                        rewriter_latencies.append(t_rewrite)
                        if rewr_res.success and not rewr_res.fallback_used and rewr_res.rewritten_query:
                            print(f"  🔄 Rewritten Query ({t_rewrite:.1f}ms): {rewr_res.rewritten_query[:75]}...")
                            rewr_dense = retrieve_dense(client, model, rewr_res.rewritten_query, limit=eval_depth)
                            merged_cands = merge_candidate_pools(dense_pts, rewr_dense, limit=eval_depth)
                            retrieved_chunks = [c.chunk_id for c in merged_cands]
                        else:
                            fallback_count += 1
                            print(f"  ⚠️ Rewriter fallback used: {rewr_res.error_message}")
                            retrieved_chunks = [c.chunk_id for c in dense_pts]

                t_query = (time.perf_counter() - t0) * 1000 + t_rewrite
                latencies.append(t_query)

                # Compute Metrics
                q_metrics = compute_metrics(retrieved_chunks, relevant_chunks, k=args.top_k)
                metric_list.append(q_metrics)

                # Display retrieved chunks (top-k)
                print("\nRetrieved chunks:")
                for rank, chunk_id in enumerate(retrieved_chunks[:args.top_k], start=1):
                    marker = " ✅ RELEVANT" if chunk_id in relevant_chunks else " ❌"
                    print(f"  Rank {rank}: {chunk_id}{marker}")

                # Display metrics
                print("\nMetrics:")
                print(f"  Hit@1       : {'YES' if q_metrics['hit@1'] else 'NO'}")
                print(f"  Hit@3       : {'YES' if q_metrics['hit@3'] else 'NO'}")
                print(f"  Hit@5       : {'YES' if q_metrics['hit@5'] else 'NO'}")
                print(f"  Hit@10      : {'YES' if q_metrics['hit@10'] else 'NO'}")
                print(f"  Hit@20      : {'YES' if q_metrics['hit@20'] else 'NO'}")
                print(f"  Precision@5 : {q_metrics['precision@5']:.4f}")
                print(f"  Recall@5    : {q_metrics['recall@5']:.4f}")
                print(f"  MRR         : {q_metrics['mrr']:.4f}")
                print(f"  Latency     : {t_query:.1f} ms")

            # Overall macro-averaged metrics
            summary = macro_average(metric_list)
            avg_lat = sum(latencies) / len(latencies)

            print("\n" + "=" * 70)
            print(f"OVERALL RETRIEVAL & RERANKING METRICS ({mode.upper()})")
            print("=" * 70)

            print(f"\nEvaluation Set   : {eval_label}")
            print(f"Questions tested : {len(questions)}")
            print(f"Average Latency  : {avg_lat:.1f} ms / query")
            if query_rewriter is not None:
                avg_rewr_lat = sum(rewriter_latencies) / len(rewriter_latencies) if rewriter_latencies else 0.0
                print(f"Rewriter Latency : {avg_rewr_lat:.1f} ms / query (Fallbacks: {fallback_count}/{len(questions)})")

            print(f"\nHit@1       : {summary['hit@1']:.2%}")
            print(f"Hit@3       : {summary['hit@3']:.2%}")
            print(f"Hit@5       : {summary['hit@5']:.2%}")
            print(f"Hit@10      : {summary['hit@10']:.2%}")
            print(f"Hit@20      : {summary['hit@20']:.2%}")
            print(f"Precision@5 : {summary['precision@5']:.2%}")
            print(f"Recall@5    : {summary['recall@5']:.2%}")
            print(f"MRR         : {summary['mrr']:.4f}")

            print("\n" + "=" * 70)
            print("EVALUATION COMPLETE")
            print("=" * 70)

    except Exception as exc:
        print(f"\n❌ ERROR during evaluation: {exc}")
        raise

    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()