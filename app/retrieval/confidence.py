"""Confidence evaluation and candidate fusion for Adaptive Query Rewriting."""

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.core.models import RetrievedChunk


class ConfidenceLevel(str, Enum):
    """Enumeration of confidence assessment tiers."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceAction(str, Enum):
    """Pipeline action dictated by confidence evaluation."""

    SKIP_REWRITE = "skip_rewrite"
    TRIGGER_REWRITE = "trigger_rewrite"


@dataclass
class ConfidenceResult:
    """Encapsulates the confidence evaluation of a retrieved candidate set."""

    is_confident: bool
    top1_score: Optional[float]
    mean_top3_score: Optional[float]
    reason: str
    score_threshold: float
    mean_threshold: float
    level: str = ConfidenceLevel.LOW.value
    action: str = ConfidenceAction.TRIGGER_REWRITE.value
    mean_top5_score: Optional[float] = None
    medium_score_threshold: Optional[float] = None
    medium_mean_threshold: Optional[float] = None
    features: Dict[str, Any] = field(default_factory=dict)


# Authoritative regex patterns for cybersecurity publications and control IDs
IDENTIFIER_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bNIST\s+SP\s+\d+-\d+(?:[A-Za-z0-9_]+)?\b", re.IGNORECASE), "NIST_SP"),
    (re.compile(r"\bSP\s+\d+-\d+(?:[A-Za-z0-9_]+)?\b", re.IGNORECASE), "SP"),
    (re.compile(r"\bNISTIR\s+\d+\b", re.IGNORECASE), "NISTIR"),
    (re.compile(r"\bFIPS\s+(?:PUB\s+)?\d+\b", re.IGNORECASE), "FIPS"),
    (re.compile(r"\bISO(?:/IEC)?\s+\d+\b", re.IGNORECASE), "ISO"),
    (re.compile(r"\bSSDF\b", re.IGNORECASE), "SSDF"),
    (re.compile(r"\bABAC\b", re.IGNORECASE), "ABAC"),
    (re.compile(r"\bRBAC\b", re.IGNORECASE), "RBAC"),
    (re.compile(r"\bPBAC\b", re.IGNORECASE), "PBAC"),
    (re.compile(r"\bFedRAMP\b", re.IGNORECASE), "FedRAMP"),
    (re.compile(r"\b(?:NIST[\s-])?CSF(?:\s*(?:v(?:er(?:sion)?)?\.?\s*)?\d+(?:\.\d+)?)?\b", re.IGNORECASE), "NIST_CSF"),
    (re.compile(r"\b(?:NIST[\s-])?RMF\b", re.IGNORECASE), "RMF"),
    (re.compile(r"\bOWASP(?:\s+Top\s+10)?\b", re.IGNORECASE), "OWASP"),
    (re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE), "CVE"),
    (re.compile(r"\bCWE(?:-|\s+)\d+\b", re.IGNORECASE), "CWE"),
    (re.compile(r"\b[A-Za-z]{2}-\d+(?:\(\d+\))?\b"), "NIST_CONTROL"),  # e.g. AC-2, IA-5(1), ac-2
]


def extract_query_identifiers(query: Optional[str]) -> List[str]:
    """Extract explicit publication, standard, or control identifiers from a query."""
    if not query or not isinstance(query, str):
        return []
    found = []
    for pat, _ in IDENTIFIER_PATTERNS:
        for m in pat.finditer(query):
            found.append(m.group().strip())
    # Deduplicate preserving original query order
    return list(dict.fromkeys(found))


def verify_identifier_in_candidate(identifier: str, candidate: Any) -> bool:
    """Verify whether an exact identifier appears in a candidate's metadata or text.

    Supports both domain model candidates (such as RetrievedChunk) and dictionary-based
    candidates with safe fallback and missing field tolerance.
    """
    if not identifier or not isinstance(identifier, str):
        return False

    ident_norm = re.sub(r"\s+", " ", identifier.strip().lower())
    if not ident_norm:
        return False

    def _get_val(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    # 1. Check metadata fields
    meta = _get_val(candidate, "metadata")
    if meta is not None:
        doc_id = str(_get_val(meta, "document_id") or "")
        src_file = str(_get_val(meta, "source_file") or "")
        section = str(_get_val(meta, "section") or "")
        combined_meta = f"{doc_id} {src_file} {section}".lower()
        if ident_norm in combined_meta:
            return True

    # 2. Check chunk text or content
    text = _get_val(candidate, "text")
    if text is None:
        text = _get_val(candidate, "content")
    if text is not None and isinstance(text, str):
        if ident_norm in text.lower():
            return True

    # 3. Check chunk_id
    cid = _get_val(candidate, "chunk_id")
    if cid is None:
        cid = _get_val(candidate, "id")
    if cid is not None and isinstance(cid, str):
        cid_norm = cid.lower().replace("_", " ").replace("-", " ")
        if ident_norm.replace("-", " ") in cid_norm:
            return True

    return False


def extract_dense_score(chunk: Any) -> Optional[float]:
    """Safely extract dense similarity score from a candidate chunk.

    Ensures BM25 scores (unbounded), RRF scores (<= 0.035), and reranker
    scores are never mistaken for dense cosine similarity scores.

    Args:
        chunk: RetrievedChunk or dict object.

    Returns:
        Float cosine similarity score in [0.0, 1.0], or None if unavailable/invalid.
    """
    if isinstance(chunk, RetrievedChunk):
        if chunk.dense_score is not None:
            s = chunk.dense_score
            if isinstance(s, (int, float)) and not (math.isnan(s) or math.isinf(s)):
                return float(s)
            return None

        # If rrf_score, bm25_score, or reranker_score is present, chunk.score is NOT dense similarity
        if chunk.rrf_score is not None or chunk.bm25_score is not None or chunk.reranker_score is not None:
            return None

        # Pure dense retriever where only chunk.score was populated
        if chunk.score is not None:
            s = chunk.score
            if isinstance(s, (int, float)) and not (math.isnan(s) or math.isinf(s)):
                if 0.0 < s <= 1.0:
                    return float(s)
            return None

    elif isinstance(chunk, dict):
        if chunk.get("dense_score") is not None:
            s = chunk["dense_score"]
            if isinstance(s, (int, float)) and not (math.isnan(s) or math.isinf(s)):
                return float(s)
            return None

        if "rrf_score" in chunk or "bm25_score" in chunk or "reranker_score" in chunk:
            return None

        if chunk.get("score") is not None:
            s = chunk["score"]
            if isinstance(s, (int, float)) and not (math.isnan(s) or math.isinf(s)):
                if 0.0 < s <= 1.0:
                    return float(s)
            return None

    return None


class ConfidenceEvaluator:
    """Evaluates retrieval candidate confidence to determine if query rewriting is needed.

    Employs a calibrated three-way confidence decision (HIGH, MEDIUM, LOW) separating
    dense score distributions from RRF candidate ordering and integrating multi-view
    lexical BM25 and exact identifier evidence.
    """

    def __init__(
        self,
        score_threshold: Optional[float] = None,
        mean_threshold: Optional[float] = None,
        min_candidates: int = 3,
        medium_score_threshold: Optional[float] = None,
        medium_mean_threshold: Optional[float] = None,
        medium_generic_top1: Optional[float] = None,
        medium_generic_mean3: Optional[float] = None,
        min_overlap: Optional[int] = None,
        min_bm25: Optional[float] = None,
        identifier_search_depth: Optional[int] = None,
    ) -> None:
        """Initialize ConfidenceEvaluator with calibrated hyperparameters.

        Args:
            score_threshold: Minimum top-1 similarity score required for HIGH confidence.
            mean_threshold: Minimum mean similarity score across top-3 candidates for HIGH confidence.
            min_candidates: Minimum number of candidate chunks with valid scores required.
            medium_score_threshold: Lower bound top-1 dense score for MEDIUM confidence.
            medium_mean_threshold: Lower bound mean-3 dense score for MEDIUM confidence.
            medium_generic_top1: Upper-medium top-1 threshold required for general queries to skip rewrite.
            medium_generic_mean3: Upper-medium mean-3 threshold required for general queries to skip rewrite.
            min_overlap: Minimum cross-modal overlap count (chunks in both dense and BM25) for consensus.
            min_bm25: Minimum top BM25 score required for lexical grounding in MEDIUM tier.
            identifier_search_depth: Maximum candidate rank depth inspected for exact identifier matches.
        """
        self.score_threshold: float = (
            score_threshold
            if score_threshold is not None
            else getattr(settings, "adaptive_confidence_threshold", 0.725)
        )
        self.mean_threshold: float = (
            mean_threshold
            if mean_threshold is not None
            else getattr(settings, "adaptive_confidence_mean_threshold", 0.700)
        )
        self.min_candidates: int = min_candidates

        self.medium_score_threshold: float = (
            medium_score_threshold
            if medium_score_threshold is not None
            else getattr(settings, "adaptive_confidence_med_threshold", 0.680)
        )
        self.medium_mean_threshold: float = (
            medium_mean_threshold
            if medium_mean_threshold is not None
            else getattr(settings, "adaptive_confidence_med_mean_threshold", 0.660)
        )
        self.medium_generic_top1: float = (
            medium_generic_top1
            if medium_generic_top1 is not None
            else getattr(settings, "adaptive_confidence_med_generic_top1", 0.705)
        )
        self.medium_generic_mean3: float = (
            medium_generic_mean3
            if medium_generic_mean3 is not None
            else getattr(settings, "adaptive_confidence_med_generic_mean3", 0.685)
        )
        self.min_overlap: int = (
            min_overlap
            if min_overlap is not None
            else getattr(settings, "adaptive_confidence_min_overlap", 6)
        )
        self.min_bm25: float = (
            min_bm25
            if min_bm25 is not None
            else getattr(settings, "adaptive_confidence_min_bm25", 25.0)
        )
        raw_depth = (
            identifier_search_depth
            if identifier_search_depth is not None
            else getattr(settings, "identifier_search_depth", 5)
        )
        try:
            depth_int = int(raw_depth)
            self.identifier_search_depth: int = depth_int if depth_int > 0 else 5
        except (ValueError, TypeError):
            self.identifier_search_depth = 5

    def evaluate(
        self,
        candidates: Sequence[RetrievedChunk],
        query: Optional[str] = None,
    ) -> ConfidenceResult:
        """Evaluate whether initial candidate retrieval results are confident.

        Implements an evidence-based three-way decision:
        - HIGH: Unambiguous dense semantic evidence. Skips rewriting.
        - MEDIUM: Evaluates multi-view lexical evidence, exact identifier verification,
                  and cross-modal overlap to decide whether initial retrieval is sufficient.
        - LOW: Insufficient evidence, missing scores, or empty pool. Triggers rewriting.

        Args:
            candidates: Sequence of RetrievedChunk objects from initial retrieval.
            query: Optional user question string to verify explicit technical identifiers.

        Returns:
            ConfidenceResult containing decision, level, action, and diagnostic metadata.
        """
        # 1. Edge Case: Empty Candidate Pool
        if not candidates:
            return ConfidenceResult(
                is_confident=False,
                level=ConfidenceLevel.LOW.value,
                action=ConfidenceAction.TRIGGER_REWRITE.value,
                top1_score=None,
                mean_top3_score=None,
                mean_top5_score=None,
                reason="empty_candidates",
                score_threshold=self.score_threshold,
                mean_threshold=self.mean_threshold,
                medium_score_threshold=self.medium_score_threshold,
                medium_mean_threshold=self.medium_mean_threshold,
                features={"candidate_count": 0, "identifier_search_depth": self.identifier_search_depth},
            )

        # 1.5. Deduplicate Candidates (Issue 1 Fix)
        # Chunks with identical chunk_id are deduplicated while preserving original candidate ordering.
        # When duplicate candidates carry different dense scores, the instance with higher similarity is retained.
        # Candidates with missing, empty, or non-string chunk_id are treated as distinct instances safely.
        unique_candidates: List[Any] = []
        seen_indices: Dict[str, int] = {}

        def _get_field(obj: Any, key: str) -> Any:
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        for c in candidates:
            cid = _get_field(c, "chunk_id")
            if cid is None:
                cid = _get_field(c, "id")
            if cid is not None and isinstance(cid, str) and cid.strip():
                clean_cid = cid.strip()
                if clean_cid in seen_indices:
                    prev_idx = seen_indices[clean_cid]
                    prev_c = unique_candidates[prev_idx]
                    prev_s = extract_dense_score(prev_c) or -1.0
                    curr_s = extract_dense_score(c) or -1.0
                    if curr_s > prev_s:
                        unique_candidates[prev_idx] = c
                    elif curr_s == prev_s:
                        prev_b = _get_field(prev_c, "bm25_score") or -1.0
                        curr_b = _get_field(c, "bm25_score") or -1.0
                        if (
                            isinstance(curr_b, (int, float))
                            and isinstance(prev_b, (int, float))
                            and curr_b > prev_b
                        ):
                            unique_candidates[prev_idx] = c
                else:
                    seen_indices[clean_cid] = len(unique_candidates)
                    unique_candidates.append(c)
            else:
                unique_candidates.append(c)

        # 2. Extract Valid Dense Scores (Issue 3: decouple from RRF order)
        valid_dense_scores: List[float] = []
        for c in unique_candidates:
            s = extract_dense_score(c)
            if s is not None:
                valid_dense_scores.append(s)

        if len(valid_dense_scores) < self.min_candidates:
            # Fallback when dense scores are missing or insufficient
            first_s = valid_dense_scores[0] if valid_dense_scores else None
            return ConfidenceResult(
                is_confident=False,
                level=ConfidenceLevel.LOW.value,
                action=ConfidenceAction.TRIGGER_REWRITE.value,
                top1_score=first_s,
                mean_top3_score=None,
                mean_top5_score=None,
                reason="missing_or_invalid_scores",
                score_threshold=self.score_threshold,
                mean_threshold=self.mean_threshold,
                medium_score_threshold=self.medium_score_threshold,
                medium_mean_threshold=self.medium_mean_threshold,
                features={
                    "valid_dense_count": len(valid_dense_scores),
                    "candidate_count": len(unique_candidates),
                    "identifier_search_depth": self.identifier_search_depth,
                },
            )

        # 3. Compute Independent Sorted Dense Statistics (Issue 3 Fix)
        sorted_dense = sorted(valid_dense_scores, reverse=True)
        top1 = sorted_dense[0]
        n3 = min(3, len(sorted_dense))
        mean3 = sum(sorted_dense[:n3]) / float(n3)
        n5 = min(5, len(sorted_dense))
        mean5 = sum(sorted_dense[:n5]) / float(n5)

        # 4. Extract BM25, Overlap, and Lexical Signals (Issue 4)
        bm25_scores = []
        for c in unique_candidates:
            b = _get_field(c, "bm25_score")
            if b is not None and isinstance(b, (int, float)) and not (math.isnan(b) or math.isinf(b)):
                bm25_scores.append(float(b))
        top_bm25 = max(bm25_scores) if bm25_scores else 0.0

        overlap_count = sum(
            1
            for c in unique_candidates
            if _get_field(c, "dense_score") is not None
            and _get_field(c, "bm25_score") is not None
        )

        # 5. Detect and Verify Exact Identifiers in Query and Chunks (Issue 4 & Issue 2)
        query_identifiers = extract_query_identifiers(query)
        verified_identifiers: List[str] = []
        if query_identifiers:
            eval_depth = max(1, self.identifier_search_depth)
            top_eval_pool = unique_candidates[: min(eval_depth, len(unique_candidates))]
            for ident in query_identifiers:
                if any(verify_identifier_in_candidate(ident, c) for c in top_eval_pool):
                    verified_identifiers.append(ident)

        has_exact_match = len(verified_identifiers) > 0

        features = {
            "candidate_count": len(unique_candidates),
            "dense_top1": round(top1, 4),
            "dense_mean3": round(mean3, 4),
            "dense_mean5": round(mean5, 4),
            "top_bm25": round(top_bm25, 2),
            "overlap_count": overlap_count,
            "query_identifiers": query_identifiers,
            "verified_identifiers": verified_identifiers,
            "has_exact_match": has_exact_match,
            "identifier_search_depth": max(1, self.identifier_search_depth),
        }

        # 6. Three-Way Confidence Decision Logic (Issue 2)
        # Tier 1: HIGH Confidence (strong dense consensus)
        if top1 >= self.score_threshold and mean3 >= self.mean_threshold:
            return ConfidenceResult(
                is_confident=True,
                level=ConfidenceLevel.HIGH.value,
                action=ConfidenceAction.SKIP_REWRITE.value,
                top1_score=top1,
                mean_top3_score=mean3,
                mean_top5_score=mean5,
                reason=f"confident_high_dense(top1={top1:.4f}>={self.score_threshold:.4f}, mean3={mean3:.4f}>={self.mean_threshold:.4f})",
                score_threshold=self.score_threshold,
                mean_threshold=self.mean_threshold,
                medium_score_threshold=self.medium_score_threshold,
                medium_mean_threshold=self.medium_mean_threshold,
                features=features,
            )

        # Tier 2: MEDIUM Confidence (mixed evidence resolved via hybrid signals)
        if top1 >= self.medium_score_threshold and mean3 >= self.medium_mean_threshold:
            # Subcase A: Exact identifier matched in top candidates, healthy BM25, and healthy medium mean
            if has_exact_match and top_bm25 >= self.min_bm25 and mean3 >= self.medium_mean_threshold:
                return ConfidenceResult(
                    is_confident=True,
                    level=ConfidenceLevel.MEDIUM.value,
                    action=ConfidenceAction.SKIP_REWRITE.value,
                    top1_score=top1,
                    mean_top3_score=mean3,
                    mean_top5_score=mean5,
                    reason=f"confident_medium_resolved_sufficient(exact_identifier={verified_identifiers}, bm25={top_bm25:.1f}>={self.min_bm25:.1f}, mean3={mean3:.4f}>={self.medium_mean_threshold:.4f})",
                    score_threshold=self.score_threshold,
                    mean_threshold=self.mean_threshold,
                    medium_score_threshold=self.medium_score_threshold,
                    medium_mean_threshold=self.medium_mean_threshold,
                    features=features,
                )

            # Subcase B: General technical query in upper-medium band with multi-view consensus
            if (
                top1 >= self.medium_generic_top1
                and mean3 >= self.medium_generic_mean3
                and overlap_count >= self.min_overlap
                and top_bm25 >= self.min_bm25
            ):
                return ConfidenceResult(
                    is_confident=True,
                    level=ConfidenceLevel.MEDIUM.value,
                    action=ConfidenceAction.SKIP_REWRITE.value,
                    top1_score=top1,
                    mean_top3_score=mean3,
                    mean_top5_score=mean5,
                    reason=f"confident_medium_resolved_sufficient(cross_modal_consensus: top1={top1:.4f}>={self.medium_generic_top1:.4f}, mean3={mean3:.4f}>={self.medium_generic_mean3:.4f}, overlap={overlap_count}>={self.min_overlap}, bm25={top_bm25:.1f}>={self.min_bm25:.1f})",
                    score_threshold=self.score_threshold,
                    mean_threshold=self.mean_threshold,
                    medium_score_threshold=self.medium_score_threshold,
                    medium_mean_threshold=self.medium_mean_threshold,
                    features=features,
                )

            # Subcase C: Medium dense evidence but insufficient hybrid grounding -> trigger rewrite
            unmet_reasons = []
            if top1 < self.medium_generic_top1:
                unmet_reasons.append(f"top1={top1:.4f}<{self.medium_generic_top1:.4f}")
            if mean3 < self.medium_generic_mean3:
                unmet_reasons.append(f"mean3={mean3:.4f}<{self.medium_generic_mean3:.4f}")
            if overlap_count < self.min_overlap:
                unmet_reasons.append(f"overlap={overlap_count}<{self.min_overlap}")
            if top_bm25 < self.min_bm25:
                unmet_reasons.append(f"bm25={top_bm25:.1f}<{self.min_bm25:.1f}")

            return ConfidenceResult(
                is_confident=False,
                level=ConfidenceLevel.MEDIUM.value,
                action=ConfidenceAction.TRIGGER_REWRITE.value,
                top1_score=top1,
                mean_top3_score=mean3,
                mean_top5_score=mean5,
                reason=f"low_confidence_medium_evidence({', '.join(unmet_reasons)})",
                score_threshold=self.score_threshold,
                mean_threshold=self.mean_threshold,
                medium_score_threshold=self.medium_score_threshold,
                medium_mean_threshold=self.medium_mean_threshold,
                features=features,
            )

        # Tier 3: LOW Confidence (weak dense evidence)
        return ConfidenceResult(
            is_confident=False,
            level=ConfidenceLevel.LOW.value,
            action=ConfidenceAction.TRIGGER_REWRITE.value,
            top1_score=top1,
            mean_top3_score=mean3,
            mean_top5_score=mean5,
            reason=f"low_dense_confidence(top1={top1:.4f}<{self.medium_score_threshold:.4f} or mean3={mean3:.4f}<{self.medium_mean_threshold:.4f})",
            score_threshold=self.score_threshold,
            mean_threshold=self.mean_threshold,
            medium_score_threshold=self.medium_score_threshold,
            medium_mean_threshold=self.medium_mean_threshold,
            features=features,
        )


def _get_candidate_metric(chunk: RetrievedChunk) -> Tuple[int, float]:
    """Return priority tier and comparable score for sorting and deduplication.

    Priority tiers ensure like-for-like comparison:
    Tier 3: RRF score (hybrid results)
    Tier 2: Dense cosine similarity
    Tier 1: BM25 score
    Tier 0: Generic score
    """
    if chunk.rrf_score is not None:
        return (3, float(chunk.rrf_score))
    if chunk.dense_score is not None:
        return (2, float(chunk.dense_score))
    if chunk.bm25_score is not None:
        return (1, float(chunk.bm25_score))
    if chunk.score is not None:
        return (0, float(chunk.score))
    return (0, 0.0)


def merge_candidate_pools(
    initial_candidates: Sequence[RetrievedChunk],
    rewritten_candidates: Sequence[RetrievedChunk],
    limit: Optional[int] = None,
) -> List[RetrievedChunk]:
    """Merge initial and rewritten candidate pools using stable chunk IDs.

    Preserves the candidate with the highest similarity score when duplicates exist,
    preventing higher-quality initial chunks from being discarded.

    Args:
        initial_candidates: Chunks retrieved with original query.
        rewritten_candidates: Chunks retrieved with rewritten query.
        limit: Maximum number of merged chunks to return.

    Returns:
        Deduplicated, sorted list of RetrievedChunk objects.
    """
    merged_map = {}

    for chunk in initial_candidates:
        merged_map[chunk.chunk_id] = chunk

    for chunk in rewritten_candidates:
        cid = chunk.chunk_id
        if cid not in merged_map:
            merged_map[cid] = chunk
        else:
            existing = merged_map[cid]
            existing_tier, existing_score = _get_candidate_metric(existing)
            new_tier, new_score = _get_candidate_metric(chunk)

            # If both have the same metric tier, compare scores directly
            if new_tier == existing_tier:
                if new_score > existing_score:
                    merged_map[cid] = chunk
            elif new_tier > existing_tier:
                # Prefer chunk with higher semantic fidelity tier (e.g. dense/RRF over pure score)
                merged_map[cid] = chunk

    # Determine dominant metric tier across the candidate pool
    has_rrf = any(c.rrf_score is not None for c in merged_map.values())

    if has_rrf:
        # Fused hybrid pool: sort by RRF score
        sorted_candidates = sorted(
            merged_map.values(),
            key=lambda c: (c.rrf_score if c.rrf_score is not None else 0.0),
            reverse=True,
        )
    else:
        # Dense or keyword pool: sort by dense_score or score
        sorted_candidates = sorted(
            merged_map.values(),
            key=lambda c: (c.dense_score if c.dense_score is not None else (c.score or 0.0)),
            reverse=True,
        )

    if limit is not None and limit > 0:
        return sorted_candidates[:limit]
    return sorted_candidates
