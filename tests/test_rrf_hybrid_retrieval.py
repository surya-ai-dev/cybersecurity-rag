"""Unit tests for Reciprocal Rank Fusion (RRF) and Hybrid Retrieval components."""

import unittest
from typing import List

from app.core.models import ChunkMetadata, RetrievedChunk
from app.retrieval.rrf import RRFFusion, get_chunk_id, reciprocal_rank_fusion


class TestRRFFusion(unittest.TestCase):
    """Test suite for RRFFusion ranking, deduplication, missing results, and determinism."""

    def test_rrf_score_calculation(self):
        """Verify exact RRF score computation with k=60."""
        fusion = RRFFusion(k=60)

        list1 = [
            {"chunk_id": "chunk_A", "text": "A text", "dense_score": 0.85},
            {"chunk_id": "chunk_B", "text": "B text", "dense_score": 0.75},
        ]
        list2 = [
            {"chunk_id": "chunk_B", "text": "B text", "bm25_score": 12.5},
            {"chunk_id": "chunk_C", "text": "C text", "bm25_score": 10.0},
        ]

        fused = fusion.fuse([list1, list2], top_k=10)

        # Expected scores with k=60:
        # chunk_A: rank 1 in list1 -> 1/(60+1) = 1/61 ~= 0.01639344
        # chunk_B: rank 2 in list1 -> 1/(60+2) = 1/62 ~= 0.01612903
        #          rank 1 in list2 -> 1/(60+1) = 1/61 ~= 0.01639344
        #          total = 1/62 + 1/61 = 123 / 3782 ~= 0.03252247
        # chunk_C: rank 2 in list2 -> 1/(60+2) = 1/62 ~= 0.01612903
        self.assertEqual(len(fused), 3)

        # chunk_B should be #1
        self.assertEqual(fused[0].chunk_id, "chunk_B")
        expected_score_b = (1.0 / 62.0) + (1.0 / 61.0)
        self.assertAlmostEqual(fused[0].rrf_score, expected_score_b, places=6)
        self.assertAlmostEqual(fused[0].score, expected_score_b, places=6)
        self.assertEqual(fused[0].dense_score, 0.75)
        self.assertEqual(fused[0].bm25_score, 12.5)

        # chunk_A should be #2
        self.assertEqual(fused[1].chunk_id, "chunk_A")
        expected_score_a = 1.0 / 61.0
        self.assertAlmostEqual(fused[1].rrf_score, expected_score_a, places=6)

        # chunk_C should be #3
        self.assertEqual(fused[2].chunk_id, "chunk_C")
        expected_score_c = 1.0 / 62.0
        self.assertAlmostEqual(fused[2].rrf_score, expected_score_c, places=6)

    def test_custom_k(self):
        """Verify custom smoothing constant k affects the score calculation."""
        fusion_k10 = RRFFusion(k=10)
        list1 = [{"chunk_id": "A", "text": "text A"}]
        fused = fusion_k10.fuse([list1], top_k=1)

        expected = 1.0 / (10 + 1)
        self.assertAlmostEqual(fused[0].rrf_score, expected, places=6)

    def test_duplicate_handling_within_single_list(self):
        """Verify duplicate chunk entries within the same candidate list do not accumulate scores."""
        fusion = RRFFusion(k=60)

        # List with duplicate chunk_A
        list_with_dups = [
            {"chunk_id": "chunk_A", "text": "A"},
            {"chunk_id": "chunk_A", "text": "A duplicate"},
            {"chunk_id": "chunk_B", "text": "B"},
        ]

        fused = fusion.fuse([list_with_dups], top_k=5)

        self.assertEqual(len(fused), 2)
        self.assertEqual(fused[0].chunk_id, "chunk_A")
        # Should only get score for rank 1: 1/(60+1)
        self.assertAlmostEqual(fused[0].rrf_score, 1.0 / 61.0, places=6)
        self.assertEqual(fused[1].chunk_id, "chunk_B")
        # chunk_B was at index 2 (rank 3 in enumerate)
        self.assertAlmostEqual(fused[1].rrf_score, 1.0 / 63.0, places=6)

    def test_missing_results_from_one_retriever(self):
        """Verify graceful handling when a retriever returns no candidates or disjoint candidates."""
        fusion = RRFFusion(k=60)

        empty_list: List[dict] = []
        dense_results = [
            {"chunk_id": "dense_1", "text": "D1"},
            {"chunk_id": "dense_2", "text": "D2"},
        ]

        # Case 1: One list is empty
        fused = fusion.fuse([dense_results, empty_list], top_k=5)
        self.assertEqual(len(fused), 2)
        self.assertEqual(fused[0].chunk_id, "dense_1")
        self.assertEqual(fused[1].chunk_id, "dense_2")

        # Case 2: Completely disjoint candidate lists
        bm25_results = [
            {"chunk_id": "bm25_1", "text": "B1"},
            {"chunk_id": "bm25_2", "text": "B2"},
        ]
        fused_disjoint = fusion.fuse([dense_results, bm25_results], top_k=10)
        self.assertEqual(len(fused_disjoint), 4)
        ids = [c.chunk_id for c in fused_disjoint]
        self.assertIn("dense_1", ids)
        self.assertIn("dense_2", ids)
        self.assertIn("bm25_1", ids)
        self.assertIn("bm25_2", ids)

    def test_deterministic_output_on_tied_scores(self):
        """Verify that score ties are broken deterministically by chunk_id."""
        fusion = RRFFusion(k=60)

        # Both chunk_Z and chunk_A appear at rank 1 in their respective single-item lists
        list1 = [{"chunk_id": "chunk_Z", "text": "Z"}]
        list2 = [{"chunk_id": "chunk_A", "text": "A"}]

        # Run multiple times to verify consistency
        for _ in range(5):
            fused = fusion.fuse([list1, list2], top_k=2)
            # Scores are identical (1/61 each), alphabetical tie-breaking must place chunk_A before chunk_Z
            self.assertEqual(fused[0].chunk_id, "chunk_A")
            self.assertEqual(fused[1].chunk_id, "chunk_Z")

    def test_retrieved_chunk_objects_support(self):
        """Verify RRFFusion works natively with RetrievedChunk instances and preserves metadata."""
        meta = ChunkMetadata(document_id="SP 800-53", section="PL-11")
        chunk1 = RetrievedChunk(chunk_id="chunk_1", text="text 1", dense_score=0.9, metadata=meta)
        chunk2 = RetrievedChunk(chunk_id="chunk_2", text="text 2", dense_score=0.8)
        chunk1_bm25 = RetrievedChunk(chunk_id="chunk_1", text="text 1", bm25_score=15.0)

        fusion = RRFFusion(k=60)
        fused = fusion.fuse([[chunk1, chunk2], [chunk1_bm25]], top_k=5)

        self.assertEqual(len(fused), 2)
        top = fused[0]
        self.assertEqual(top.chunk_id, "chunk_1")
        self.assertEqual(top.dense_score, 0.9)
        self.assertEqual(top.bm25_score, 15.0)
        self.assertEqual(top.metadata.document_id, "SP 800-53")
        self.assertEqual(top.metadata.section, "PL-11")
        self.assertEqual(top["rrf_rank"], 1)

    def test_top_k_limiting(self):
        """Verify top_k truncation limits the number of returned chunks."""
        fusion = RRFFusion(k=60)
        list1 = [{"chunk_id": f"chunk_{i}", "text": f"text {i}"} for i in range(20)]

        fused = fusion.fuse([list1], top_k=5)
        self.assertEqual(len(fused), 5)

    def test_weighted_rrf(self):
        """Verify weighted RRF score computation scales individual list contributions."""
        fusion = RRFFusion(k=60, weights=[0.8, 0.2])
        list1 = [{"chunk_id": "chunk_dense", "text": "Dense 1"}]
        list2 = [{"chunk_id": "chunk_bm25", "text": "BM25 1"}]

        fused = fusion.fuse([list1, list2], top_k=2)
        self.assertEqual(len(fused), 2)
        # chunk_dense should have 0.8 / 61
        expected_dense = 0.8 * (1.0 / 61.0)
        # chunk_bm25 should have 0.2 / 61
        expected_bm25 = 0.2 * (1.0 / 61.0)

        self.assertEqual(fused[0].chunk_id, "chunk_dense")
        self.assertAlmostEqual(fused[0].rrf_score, expected_dense, places=6)
        self.assertEqual(fused[1].chunk_id, "chunk_bm25")
        self.assertAlmostEqual(fused[1].rrf_score, expected_bm25, places=6)


if __name__ == "__main__":
    unittest.main()
