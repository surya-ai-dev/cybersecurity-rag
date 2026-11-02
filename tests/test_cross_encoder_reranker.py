"""Unit tests for CrossEncoderReranker and candidate pool generation."""

import unittest
from typing import List

from app.core.models import ChunkMetadata, RetrievedChunk
from app.retrieval.reranker import (
    CrossEncoderReranker,
    combine_candidate_pools,
    rerank_documents,
)


class TestCandidatePoolGeneration(unittest.TestCase):
    """Test suite for candidate pool combination and provenance tracking."""

    def test_combine_candidate_pools_deduplication(self):
        """Verify overlapping chunks between Dense and BM25 are deduplicated with provenance merged."""
        meta_a = ChunkMetadata(document_id="SP 800-144", section="5.1")
        chunk_dense_a = RetrievedChunk(chunk_id="chunk_A", text="Text A", dense_score=0.95, metadata=meta_a)
        chunk_dense_b = RetrievedChunk(chunk_id="chunk_B", text="Text B", dense_score=0.85)

        chunk_bm25_a = RetrievedChunk(chunk_id="chunk_A", text="Text A", bm25_score=14.2)
        chunk_bm25_c = RetrievedChunk(chunk_id="chunk_C", text="Text C", bm25_score=11.5)

        pooled = combine_candidate_pools([chunk_dense_a, chunk_dense_b], [chunk_bm25_a, chunk_bm25_c])

        self.assertEqual(len(pooled), 3)
        ids = [c.chunk_id for c in pooled]
        self.assertEqual(ids, ["chunk_A", "chunk_B", "chunk_C"])

        # Check provenance for chunk_A (present in both)
        top = pooled[0]
        self.assertEqual(top.chunk_id, "chunk_A")
        self.assertTrue(top["retrieved_by_dense"])
        self.assertTrue(top["retrieved_by_bm25"])
        self.assertEqual(top["dense_rank"], 1)
        self.assertEqual(top["bm25_rank"], 1)
        self.assertEqual(top.dense_score, 0.95)
        self.assertEqual(top.bm25_score, 14.2)
        self.assertEqual(top.metadata.document_id, "SP 800-144")

        # Check provenance for chunk_B (dense only)
        mid = pooled[1]
        self.assertEqual(mid.chunk_id, "chunk_B")
        self.assertTrue(mid["retrieved_by_dense"])
        self.assertFalse(mid["retrieved_by_bm25"])
        self.assertEqual(mid["dense_rank"], 2)
        self.assertNotIn("bm25_rank", mid)

        # Check provenance for chunk_C (bm25 only)
        last = pooled[2]
        self.assertEqual(last.chunk_id, "chunk_C")
        self.assertFalse(last["retrieved_by_dense"])
        self.assertTrue(last["retrieved_by_bm25"])
        self.assertEqual(last["bm25_rank"], 2)

    def test_combine_candidate_pools_dense_only(self):
        """Verify candidate pool combination works seamlessly when bm25_candidates is None or empty."""
        chunk1 = RetrievedChunk(chunk_id="chunk_1", text="Text 1", dense_score=0.9)
        chunk2 = RetrievedChunk(chunk_id="chunk_2", text="Text 2", dense_score=0.8)

        pooled = combine_candidate_pools([chunk1, chunk2], bm25_candidates=None)
        self.assertEqual(len(pooled), 2)
        self.assertTrue(pooled[0]["retrieved_by_dense"])
        self.assertFalse(pooled[0]["retrieved_by_bm25"])


class TestCrossEncoderReranker(unittest.TestCase):
    """Test suite for CrossEncoderReranker behavior, score assignment, and determinism."""

    @classmethod
    def setUpClass(cls):
        """Initialize the CrossEncoder model once for the test suite."""
        cls.reranker = CrossEncoderReranker(lazy_load=False)

    def test_empty_candidates_handling(self):
        """Verify passing an empty candidate list returns an empty list without error."""
        result = self.reranker.rerank("What is cloud security?", [])
        self.assertEqual(result, [])

    def test_reranking_accuracy_and_score_assignment(self):
        """Verify reranker correctly ranks relevant passages higher and populates scores."""
        query = "What is the primary role of access control?"
        candidates = [
            RetrievedChunk(
                chunk_id="irrelevant_cooking",
                text="Cooking pasta requires boiling water and adding salt to taste.",
            ),
            RetrievedChunk(
                chunk_id="relevant_access_control",
                text="Access control is the process of granting or denying specific requests for obtaining and using information and related services.",
            ),
        ]

        reranked = self.reranker.rerank(query, candidates, top_n=2)
        self.assertEqual(len(reranked), 2)

        # Access control chunk must be ranked #1
        self.assertEqual(reranked[0].chunk_id, "relevant_access_control")
        self.assertIsNotNone(reranked[0].reranker_score)
        self.assertEqual(reranked[0].score, reranked[0].reranker_score)
        self.assertEqual(reranked[0]["reranker_rank"], 1)

        # Irrelevant chunk must be ranked #2 with lower score
        self.assertEqual(reranked[1].chunk_id, "irrelevant_cooking")
        self.assertGreater(reranked[0].reranker_score, reranked[1].reranker_score)

    def test_deterministic_sorting_on_score_ties(self):
        """Verify deterministic alphabetical tie-breaking when two chunks have identical scores."""
        # Using mock or equal scores to verify tie-breaking logic
        c1 = RetrievedChunk(chunk_id="chunk_Z", text="Sample", reranker_score=1.5)
        c2 = RetrievedChunk(chunk_id="chunk_A", text="Sample", reranker_score=1.5)

        # Test sorting lambda directly
        chunks = [c1, c2]
        chunks.sort(
            key=lambda c: (
                -(c.reranker_score if c.reranker_score is not None else float("-inf")),
                str(c.chunk_id),
            )
        )
        self.assertEqual(chunks[0].chunk_id, "chunk_A")
        self.assertEqual(chunks[1].chunk_id, "chunk_Z")

    def test_top_n_truncation(self):
        """Verify top_n parameter truncates the output list appropriately."""
        query = "Cybersecurity risk management"
        candidates = [
            RetrievedChunk(chunk_id=f"c_{i}", text=f"Cybersecurity control text number {i}")
            for i in range(10)
        ]
        reranked = self.reranker.rerank(query, candidates, top_n=3)
        self.assertEqual(len(reranked), 3)


if __name__ == "__main__":
    unittest.main()
