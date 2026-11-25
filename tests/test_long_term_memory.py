"""Unit tests for LongTermMemory and domain scope extraction (Step 3 / Module 4)."""

from array import array
import unittest
from unittest.mock import patch

from app.conversation.long_term_memory import LongTermMemory, extract_domain_scope
from app.conversation.storage import SQLiteMemoryStore
from app.core.models import MemoryFact


class TestDomainScopeExtraction(unittest.TestCase):
    """Verify identifier reuse from confidence.py and architecture scope extraction."""

    def test_extracts_standards_controls_cves_and_deployment_scope(self):
        text = "Compare NIST SP 800-53 ac-2 with CVE-2024-1234 and Zero Trust under SaaS."
        facts = extract_domain_scope(text, session_id="sess-1", source_turn=2)
        by_key = {(f.category, f.key): f for f in facts}

        self.assertIn(("standard", "NIST SP 800-53"), by_key)
        self.assertIn(("control", "AC-2"), by_key)
        self.assertIn(("identifier", "CVE-2024-1234"), by_key)
        self.assertIn(("environment", "SaaS"), by_key)
        self.assertIn(("environment", "Zero Trust"), by_key)
        self.assertEqual(by_key[("control", "AC-2")].source_turn, 2)

    def test_reuses_confidence_extract_query_identifiers(self):
        with patch(
            "app.conversation.long_term_memory.extract_query_identifiers",
            return_value=["SP 800-144"],
        ) as mock_extract:
            facts = extract_domain_scope("anything", session_id="sess-x")
            mock_extract.assert_called_once_with("anything")
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0].key, "SP 800-144")


class TestLongTermMemory(unittest.TestCase):
    """Verify fact deduplication and semantic cosine similarity recall."""

    def test_deduplication_across_turns_with_sqlite_store(self):
        with SQLiteMemoryStore(":memory:") as store:
            ltm = LongTermMemory(store=store)
            ltm.record_turn(
                "sess-dedup",
                "What are security risks in NIST SP 800-144 for SaaS?",
                source_turn=1,
            )
            ltm.record_turn(
                "sess-dedup",
                "What else does NIST SP 800-144 say about multi-tenant SaaS?",
                source_turn=4,
            )

            facts = ltm.get_session_facts("sess-dedup")
            keys = [(f.category, f.key) for f in facts]
            self.assertEqual(len(keys), len(set(keys)))
            sp_fact = [f for f in facts if f.key == "NIST SP 800-144"][0]
            self.assertEqual(sp_fact.source_turn, 4)

    def test_semantic_cosine_recall_ranking_and_edge_cases(self):
        vectors = {
            "cloud storage encryption": [1.0, 0.0, 0.0],
            "NIST SP 800-146: Encrypted cloud storage controls": [0.95, 0.31, 0.0],
            "Zero Trust: Microsegmentation policy engine": [0.0, 1.0, 0.0],
            "Mismatched Dim: Broken embedding": [1.0, 0.0],
            "Zero Vector: Null norm embedding": [0.0, 0.0, 0.0],
        }

        def fake_embed(text: str):
            for key, vec in vectors.items():
                if key in text:
                    return vec
            return [0.0, 0.0, 1.0]

        with SQLiteMemoryStore(":memory:") as store:
            ltm = LongTermMemory(store=store, embed_fn=fake_embed, min_similarity=0.55)
            store.create_session("sess-1")
            store.create_session("sess-2")

            ltm.upsert_fact(
                MemoryFact("f1", "sess-1", "standard", "NIST SP 800-146", "Encrypted cloud storage controls"),
            )
            ltm.upsert_fact(
                MemoryFact("f2", "sess-1", "environment", "Zero Trust", "Microsegmentation policy engine"),
            )
            # Directly insert malformed/mismatched and zero-norm rows into SQLite to test robustness
            ltm.upsert_fact(
                MemoryFact("f3", "sess-1", "standard", "Mismatched", "Mismatched vector"),
                embedding=[1.0, 0.0],  # wrong dimension (2 vs 3)
            )
            store.upsert_fact(
                MemoryFact("f4", "sess-1", "standard", "ZeroVec", "Zero vector fact"),
                embedding=[0.0, 0.0, 0.0],
            )
            ltm.upsert_fact(
                MemoryFact("f5", "sess-2", "standard", "NIST SP 800-146", "Encrypted cloud storage controls (other)"),
            )

            # Same-session semantic recall: only f1 matches >= 0.55; f2 is orthogonal, f3/f4 invalid
            hits = ltm.recall("cloud storage encryption", session_id="sess-1", top_k=3)
            self.assertEqual([h.fact_id for h in hits], ["f1"])

            # Cross-session recall returns both sess-1 and sess-2 matches capped by top_k
            cross_hits = ltm.recall(
                "cloud storage encryption",
                session_id="sess-1",
                top_k=5,
                include_cross_session=True,
            )
            self.assertEqual({h.fact_id for h in cross_hits}, {"f1", "f5"})

            # Zero-norm query embedding safely returns empty semantic hits without crashing
            with patch.object(ltm, "embed_fn", return_value=[0.0, 0.0, 0.0]):
                zero_q_hits = ltm.recall("anything", session_id="sess-1", top_k=3)
                self.assertEqual(zero_q_hits, [])

    def test_in_memory_mode_without_sqlite_store(self):
        ltm = LongTermMemory(store=None, embed_fn=None)
        ltm.record_turn("sess-mem", "Review NIST SP 800-207 for Kubernetes microservices.", source_turn=1)
        recalled = ltm.recall("What else applies?", session_id="sess-mem", top_k=5)
        recalled_keys = {f.key for f in recalled}
        self.assertEqual(recalled_keys, {"NIST SP 800-207", "Kubernetes", "microservices"})


if __name__ == "__main__":
    unittest.main()
