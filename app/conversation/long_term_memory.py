"""Long-term cybersecurity domain scope extraction and episodic recall memory."""

from array import array
from datetime import datetime, timezone
import logging
import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import uuid

from app.conversation.storage import SQLiteMemoryStore
from app.core.models import MemoryFact
from app.retrieval.confidence import extract_query_identifiers

logger = logging.getLogger(__name__)

# Canonical cybersecurity deployment & architectural scope cues (non-ID scope)
_DEPLOYMENT_SCOPE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bSaaS\b", re.IGNORECASE), "SaaS"),
    (re.compile(r"\bPaaS\b", re.IGNORECASE), "PaaS"),
    (re.compile(r"\bIaaS\b", re.IGNORECASE), "IaaS"),
    (re.compile(r"\bpublic\s+cloud\b", re.IGNORECASE), "public cloud"),
    (re.compile(r"\bprivate\s+cloud\b", re.IGNORECASE), "private cloud"),
    (re.compile(r"\bhybrid\s+cloud\b", re.IGNORECASE), "hybrid cloud"),
    (re.compile(r"\bmulti-?tenant\b", re.IGNORECASE), "multi-tenant"),
    (re.compile(r"\bzero\s+trust\b", re.IGNORECASE), "Zero Trust"),
    (re.compile(r"\bmicroservices?\b", re.IGNORECASE), "microservices"),
    (re.compile(r"\bkubernetes\b", re.IGNORECASE), "Kubernetes"),
    (re.compile(r"\bBYOD\b", re.IGNORECASE), "BYOD"),
]

_NIST_CONTROL_ID_RE = re.compile(r"^[A-Za-z]{2}-\d+(?:\(\d+\))?$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_identifier_fact(ident: str) -> Tuple[str, str, str]:
    """Classify and normalize an identifier extracted by extract_query_identifiers."""
    collapsed = " ".join(ident.strip().split())
    if _NIST_CONTROL_ID_RE.match(collapsed):
        key = collapsed.upper()
        return ("control", key, f"Active referenced control: {key}")

    upper = collapsed.upper()
    if upper.startswith("CVE-") or upper.startswith("CWE"):
        key = upper.replace(" ", "-")
        return ("identifier", key, f"Active referenced identifier: {key}")

    return ("standard", collapsed, f"Active referenced standard: {collapsed}")


def extract_domain_scope(
    text: str,
    session_id: str,
    source_turn: Optional[int] = None,
) -> List[MemoryFact]:
    """Extract cybersecurity standards, controls, and deployment scope MemoryFacts."""
    if not text or not isinstance(text, str):
        return []

    now = _utc_now_iso()
    facts_by_key: Dict[Tuple[str, str], MemoryFact] = {}

    # Reuse canonical identifier extraction from app/retrieval/confidence.py
    raw_idents = extract_query_identifiers(text)
    normalized_lower = [" ".join(i.strip().split()).lower() for i in raw_idents]
    filtered_idents = [
        ident
        for idx, ident in enumerate(raw_idents)
        if not any(
            j != idx
            and len(normalized_lower[j]) > len(normalized_lower[idx])
            and normalized_lower[idx] in normalized_lower[j]
            for j in range(len(raw_idents))
        )
    ]

    for ident in filtered_idents:
        category, key, value = _normalize_identifier_fact(ident)
        if (category, key) not in facts_by_key:
            facts_by_key[(category, key)] = MemoryFact(
                fact_id=str(uuid.uuid4()),
                session_id=session_id,
                category=category,
                key=key,
                value=value,
                source_turn=source_turn,
                confidence=1.0,
                updated_at=now,
            )

    # Detect deployment & architecture scope terms
    for pattern, canonical in _DEPLOYMENT_SCOPE_PATTERNS:
        if pattern.search(text):
            if ("environment", canonical) not in facts_by_key:
                facts_by_key[("environment", canonical)] = MemoryFact(
                    fact_id=str(uuid.uuid4()),
                    session_id=session_id,
                    category="environment",
                    key=canonical,
                    value=f"Active architecture/deployment scope: {canonical}",
                    source_turn=source_turn,
                    confidence=1.0,
                    updated_at=now,
                )

    return list(facts_by_key.values())


def _normalize_vector(vec: Sequence[float]) -> Optional[List[float]]:
    """Convert and L2-normalize a numeric vector; return None on invalid or zero vectors."""
    if not vec:
        return None
    cleaned: List[float] = []
    sq_sum = 0.0
    for val in vec:
        if not isinstance(val, (int, float)):
            return None
        fval = float(val)
        if not math.isfinite(fval):
            return None
        cleaned.append(fval)
        sq_sum += fval * fval

    if sq_sum <= 0.0:
        return None
    norm = math.sqrt(sq_sum)
    return [x / norm for x in cleaned]


def _decode_float32_blob(blob: bytes, expected_dim: int) -> Optional[List[float]]:
    """Decode serialized float32 bytes safely and validate length matches dim."""
    if not blob or expected_dim <= 0:
        return None
    arr = array("f")
    try:
        arr.frombytes(blob)
    except Exception:
        return None
    if len(arr) != expected_dim:
        return None
    return list(arr)


class LongTermMemory:
    """Tracks durable cybersecurity scope facts and semantic episodic recall."""

    def __init__(
        self,
        store: Optional[SQLiteMemoryStore] = None,
        embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
        min_similarity: float = 0.55,
    ) -> None:
        self.store: Optional[SQLiteMemoryStore] = store
        self.embed_fn: Optional[Callable[[str], Sequence[float]]] = embed_fn
        self.min_similarity: float = float(min_similarity)
        self._in_memory_facts: Dict[
            Tuple[str, str, str], Tuple[MemoryFact, Optional[List[float]]]
        ] = {}

    def _compute_embedding(self, text: str) -> Optional[List[float]]:
        if self.embed_fn is None or not text.strip():
            return None
        try:
            raw = self.embed_fn(text)
            return _normalize_vector(raw)
        except Exception as exc:
            logger.warning("LongTermMemory embedding computation failed: %s", exc)
            return None

    def upsert_fact(
        self,
        fact: MemoryFact,
        embedding: Optional[Sequence[float]] = None,
    ) -> None:
        """Persist or update a MemoryFact with optional semantic vector."""
        resolved_emb: Optional[List[float]] = None
        if embedding is not None:
            resolved_emb = _normalize_vector(embedding)
        elif self.embed_fn is not None:
            resolved_emb = self._compute_embedding(f"{fact.key}: {fact.value}")

        if self.store is not None:
            self.store.upsert_fact(fact, embedding=resolved_emb)
        else:
            dedup_key = (fact.session_id, fact.category, fact.key)
            existing = self._in_memory_facts.get(dedup_key)
            if existing is not None:
                # Preserve original fact_id while updating metadata
                fact = MemoryFact(
                    fact_id=existing[0].fact_id,
                    session_id=fact.session_id,
                    category=fact.category,
                    key=fact.key,
                    value=fact.value,
                    source_turn=fact.source_turn,
                    confidence=fact.confidence,
                    updated_at=fact.updated_at or _utc_now_iso(),
                )
            self._in_memory_facts[dedup_key] = (fact, resolved_emb)

    def record_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str = "",
        source_turn: Optional[int] = None,
    ) -> List[MemoryFact]:
        """Extract durable scope facts from a user turn and upsert them."""
        del assistant_message  # Scope is extracted from user intent to avoid chunk noise.
        facts = extract_domain_scope(
            user_message,
            session_id=session_id,
            source_turn=source_turn,
        )
        for fact in facts:
            self.upsert_fact(fact)
        return facts

    def get_session_facts(
        self,
        session_id: str,
        category: Optional[str] = None,
    ) -> List[MemoryFact]:
        """Return all stored facts for a specific session."""
        if self.store is not None:
            return self.store.get_facts(session_id=session_id, category=category)

        results = [
            fact
            for (sid, cat, _), (fact, _) in self._in_memory_facts.items()
            if sid == session_id and (category is None or cat == category)
        ]
        results.sort(key=lambda f: f.updated_at, reverse=True)
        return results

    def recall(
        self,
        query: str,
        session_id: str,
        top_k: int = 3,
        include_cross_session: bool = False,
    ) -> List[MemoryFact]:
        """Retrieve up to top_k relevant facts via semantic cosine recall + session scope."""
        if top_k <= 0:
            return []

        target_session = None if include_cross_session else session_id
        q_norm = self._compute_embedding(query) if (query and self.embed_fn is not None) else None

        scored: List[Tuple[float, MemoryFact]] = []
        seen_ids = set()

        if q_norm is not None:
            if self.store is not None:
                emb_rows = self.store.get_fact_embeddings(session_id=target_session)
                candidates_with_vecs = [
                    (fact, _decode_float32_blob(blob, dim))
                    for fact, blob, dim in emb_rows
                ]
            else:
                candidates_with_vecs = [
                    (fact, vec)
                    for (sid, _, _), (fact, vec) in self._in_memory_facts.items()
                    if target_session is None or sid == target_session
                ]

            for fact, raw_vec in candidates_with_vecs:
                if raw_vec is None or len(raw_vec) != len(q_norm):
                    continue
                v_norm = _normalize_vector(raw_vec)
                if v_norm is None:
                    continue
                sim = sum(a * b for a, b in zip(q_norm, v_norm))
                if sim >= self.min_similarity:
                    scored.append((sim, fact))

            scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)

        selected: List[MemoryFact] = []
        for _, fact in scored:
            if fact.fact_id not in seen_ids:
                selected.append(fact)
                seen_ids.add(fact.fact_id)
                if len(selected) >= top_k:
                    return selected

        # Backfill remaining capacity with deterministic active-session scope facts
        # that do not carry embeddings (e.g. non-semantic scope when embed_fn is None).
        if self.store is not None:
            session_facts = self.store.get_facts(session_id=session_id)
            emb_fact_ids = (
                {ef.fact_id for ef, _, _ in self.store.get_fact_embeddings(session_id=session_id)}
                if self.embed_fn is not None
                else set()
            )
        else:
            session_facts = self.get_session_facts(session_id)
            emb_fact_ids = (
                {
                    fact.fact_id
                    for (sid, _, _), (fact, vec) in self._in_memory_facts.items()
                    if sid == session_id and vec is not None
                }
                if self.embed_fn is not None
                else set()
            )

        for fact in session_facts:
            if fact.fact_id in seen_ids or fact.fact_id in emb_fact_ids:
                continue
            selected.append(fact)
            seen_ids.add(fact.fact_id)
            if len(selected) >= top_k:
                break

        return selected
