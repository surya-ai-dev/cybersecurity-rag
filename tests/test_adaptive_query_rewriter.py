"""Unit tests for Adaptive Query Rewriting in Cybersecurity RAG."""

import math
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.core.models import ChunkMetadata, RetrievedChunk
from app.pipeline.engine import RAGEngine
from app.retrieval.confidence import (
    ConfidenceEvaluator,
    ConfidenceResult,
    merge_candidate_pools,
)
from app.retrieval.query_rewriter import QueryRewriter, RewriteResult


class TestConfidenceEvaluator(unittest.TestCase):
    """Unit tests for ConfidenceEvaluator."""

    def setUp(self):
        self.evaluator = ConfidenceEvaluator(
            score_threshold=0.735,
            mean_threshold=0.700,
            min_candidates=3,
        )

    def test_high_confidence_results_identified_correctly(self):
        """High-confidence results (top1 >= 0.735 and mean3 >= 0.700) should evaluate as confident."""
        cands = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.760),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.740),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.720),
            RetrievedChunk(chunk_id="c4", text="text4", dense_score=0.700),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertTrue(res.is_confident)
        self.assertAlmostEqual(res.top1_score, 0.760)
        self.assertAlmostEqual(res.mean_top3_score, (0.760 + 0.740 + 0.720) / 3.0)
        self.assertIn("confident", res.reason)

    def test_low_confidence_results_trigger_rewriting(self):
        """Low-confidence results (top1 < 0.735 or mean3 < 0.700) evaluate as is_confident=False."""
        cands = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.690),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.670),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.660),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertAlmostEqual(res.top1_score, 0.690)
        self.assertIn("low_confidence", res.reason)

    def test_missing_or_invalid_scores_handled_safely(self):
        """Candidates with None, NaN, inf, or empty scores must not be classified as confident."""
        # Case 1: Empty candidates
        res_empty = self.evaluator.evaluate([])
        self.assertFalse(res_empty.is_confident)
        self.assertEqual(res_empty.reason, "empty_candidates")

        # Case 2: None scores
        cands_none = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=None),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=None),
        ]
        res_none = self.evaluator.evaluate(cands_none)
        self.assertFalse(res_none.is_confident)
        self.assertEqual(res_none.reason, "missing_or_invalid_scores")

        # Case 3: NaN and inf scores
        cands_nan = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=float("nan")),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=float("inf")),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.75),
        ]
        res_nan = self.evaluator.evaluate(cands_nan)
        self.assertFalse(res_nan.is_confident)
        self.assertEqual(res_nan.reason, "missing_or_invalid_scores")

    def test_rrf_and_bm25_scores_never_confused_with_dense(self):
        """Pure RRF or BM25 candidates without dense scores must not be treated as dense similarity."""
        # Chunks with RRF score (~0.016) and score set to rrf_score
        cands_rrf = [
            RetrievedChunk(chunk_id="c1", text="text1", score=0.01639, rrf_score=0.01639),
            RetrievedChunk(chunk_id="c2", text="text2", score=0.01612, rrf_score=0.01612),
            RetrievedChunk(chunk_id="c3", text="text3", score=0.01587, rrf_score=0.01587),
        ]
        res_rrf = self.evaluator.evaluate(cands_rrf)
        self.assertFalse(res_rrf.is_confident)
        self.assertIsNone(res_rrf.top1_score)
        self.assertEqual(res_rrf.reason, "missing_or_invalid_scores")

        # Chunks with BM25 score (~15.0) and score set to bm25_score
        cands_bm25 = [
            RetrievedChunk(chunk_id="c1", text="text1", score=18.5, bm25_score=18.5),
            RetrievedChunk(chunk_id="c2", text="text2", score=14.2, bm25_score=14.2),
            RetrievedChunk(chunk_id="c3", text="text3", score=11.0, bm25_score=11.0),
        ]
        res_bm25 = self.evaluator.evaluate(cands_bm25)
        self.assertFalse(res_bm25.is_confident)
        self.assertIsNone(res_bm25.top1_score)
        self.assertEqual(res_bm25.reason, "missing_or_invalid_scores")

    def test_hybrid_candidates_evaluated_on_dense_scores_only(self):
        """In hybrid results, chunks with valid dense_score are evaluated accurately regardless of RRF score."""
        cands_hybrid = [
            RetrievedChunk(chunk_id="c1", text="text1", score=0.032, rrf_score=0.032, dense_score=0.78, bm25_score=12.0),
            RetrievedChunk(chunk_id="c2", text="text2", score=0.028, rrf_score=0.028, dense_score=0.75, bm25_score=10.0),
            RetrievedChunk(chunk_id="c3", text="text3", score=0.025, rrf_score=0.025, dense_score=0.72),
        ]
        res_hybrid = self.evaluator.evaluate(cands_hybrid)
        self.assertTrue(res_hybrid.is_confident)
        self.assertAlmostEqual(res_hybrid.top1_score, 0.78)
        self.assertAlmostEqual(res_hybrid.mean_top3_score, (0.78 + 0.75 + 0.72) / 3.0)


class TestCandidateMergeAndDeduplication(unittest.TestCase):
    """Unit tests for merge_candidate_pools."""

    def test_candidate_deduplication_and_score_retention(self):
        """Verify duplicate chunks are merged, preserving the instance with the higher score."""
        meta_a = ChunkMetadata(document_id="SP 800-144", section="5.1")
        init_a = RetrievedChunk(chunk_id="c_A", text="Text A Initial", dense_score=0.70, metadata=meta_a)
        init_b = RetrievedChunk(chunk_id="c_B", text="Text B Initial", dense_score=0.65)

        rewr_a = RetrievedChunk(chunk_id="c_A", text="Text A Rewritten", dense_score=0.82)
        rewr_c = RetrievedChunk(chunk_id="c_C", text="Text C Rewritten", dense_score=0.78)

        merged = merge_candidate_pools([init_a, init_b], [rewr_a, rewr_c], limit=5)

        self.assertEqual(len(merged), 3)
        self.assertEqual([c.chunk_id for c in merged], ["c_A", "c_C", "c_B"])
        # c_A should have the higher rewritten score 0.82
        self.assertEqual(merged[0].dense_score, 0.82)
        self.assertEqual(merged[1].dense_score, 0.78)
        self.assertEqual(merged[2].dense_score, 0.65)

    def test_merge_candidate_pools_truncation(self):
        """Verify candidate pool limit correctly truncates the merged list."""
        cands1 = [RetrievedChunk(chunk_id=f"c_{i}", text=f"t_{i}", dense_score=0.5 + i * 0.05) for i in range(5)]
        cands2 = [RetrievedChunk(chunk_id=f"c_{i+5}", text=f"t_{i+5}", dense_score=0.6 + i * 0.05) for i in range(5)]

        merged = merge_candidate_pools(cands1, cands2, limit=4)
        self.assertEqual(len(merged), 4)


class TestAdaptivePipelineIntegration(unittest.TestCase):
    """Integration tests for adaptive rewriting flow in RAGEngine."""

    def setUp(self):
        self.mock_retriever = MagicMock()
        self.mock_reranker = MagicMock()
        self.mock_reranker.rerank.side_effect = lambda q, cands, top_n: cands[:top_n]
        self.mock_llm_provider = MagicMock()
        self.mock_llm_provider.generate.return_value = "Authoritative grounded answer."
        self.mock_memory = MagicMock()
        self.mock_memory.get_messages.return_value = []
        self.mock_rewriter = MagicMock()

        self.engine = RAGEngine(
            retriever=self.mock_retriever,
            reranker=self.mock_reranker,
            llm_provider=self.mock_llm_provider,
            memory=self.mock_memory,
            retrieval_query_rewriter=self.mock_rewriter,
            confidence_evaluator=ConfidenceEvaluator(score_threshold=0.735, mean_threshold=0.700),
            retrieval_top_k=5,
            rerank_top_n=3,
        )

    def test_high_confidence_skips_rewriting(self):
        """When initial retrieval is confident, query rewriter should not be called."""
        high_conf_cands = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.78),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.75),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.73),
        ]
        self.mock_retriever.retrieve.return_value = high_conf_cands

        with patch.object(settings, "enable_adaptive_query_rewriting", True), \
             patch.object(settings, "enable_query_rewriting", False):
            resp = self.engine.query("What is NIST SP 800-53?", stream=False)

            # Retriever called once with original question
            self.mock_retriever.retrieve.assert_called_once_with("What is NIST SP 800-53?", top_k=5)
            # Rewriter NEVER called
            self.mock_rewriter.rewrite.assert_not_called()
            # Reranker called with original question
            self.mock_reranker.rerank.assert_called_once_with("What is NIST SP 800-53?", high_conf_cands, top_n=3)
            # Response properties preserved
            self.assertEqual(resp.question, "What is NIST SP 800-53?")
            self.assertEqual(resp.standalone_question, "What is NIST SP 800-53?")

    def test_low_confidence_triggers_rewriting_and_merges_candidates(self):
        """When initial retrieval is low-confidence, rewriter is invoked and candidate pools merged."""
        low_conf_cands = [
            RetrievedChunk(chunk_id="c_init1", text="text init 1", dense_score=0.68),
            RetrievedChunk(chunk_id="c_init2", text="text init 2", dense_score=0.65),
            RetrievedChunk(chunk_id="c_init3", text="text init 3", dense_score=0.62),
        ]
        rewr_cands = [
            RetrievedChunk(chunk_id="c_rewr1", text="text rewr 1", dense_score=0.85),
            RetrievedChunk(chunk_id="c_init1", text="text init 1", dense_score=0.79),
        ]

        # First call returns low_conf_cands, second call returns rewr_cands
        self.mock_retriever.retrieve.side_effect = [low_conf_cands, rewr_cands]
        self.mock_rewriter.rewrite.return_value = RewriteResult(
            original_query="What are cloud monitoring challenges?",
            rewritten_query="public cloud security monitoring challenges event logs provider controls",
            success=True,
            fallback_used=False,
            latency_ms=250.0,
        )

        with patch.object(settings, "enable_adaptive_query_rewriting", True), \
             patch.object(settings, "enable_query_rewriting", False):
            resp = self.engine.query("What are cloud monitoring challenges?", stream=False)

            # Rewriter was called once
            self.mock_rewriter.rewrite.assert_called_once_with("What are cloud monitoring challenges?")
            # Retriever was called twice
            self.assertEqual(self.mock_retriever.retrieve.call_count, 2)
            first_call_arg = self.mock_retriever.retrieve.call_args_list[0][0][0]
            second_call_arg = self.mock_retriever.retrieve.call_args_list[1][0][0]
            self.assertEqual(first_call_arg, "What are cloud monitoring challenges?")
            self.assertEqual(second_call_arg, "public cloud security monitoring challenges event logs provider controls")

            # Standalone question preserved in prompt builder & memory
            prompt_sent = self.mock_llm_provider.generate.call_args[0][0]
            self.assertIn("What are cloud monitoring challenges?", prompt_sent)
            self.assertNotIn("public cloud security monitoring challenges event logs", prompt_sent)
            self.mock_memory.add_message.assert_called_once_with(
                "What are cloud monitoring challenges?",
                "Authoritative grounded answer.",
            )

    def test_rewriter_failure_or_timeout_preserves_initial_results(self):
        """When rewriter fails, times out, or triggers fallback, initial candidates are safely preserved."""
        low_conf_cands = [
            RetrievedChunk(chunk_id="c_init1", text="text init 1", dense_score=0.65),
            RetrievedChunk(chunk_id="c_init2", text="text init 2", dense_score=0.62),
            RetrievedChunk(chunk_id="c_init3", text="text init 3", dense_score=0.60),
        ]
        self.mock_retriever.retrieve.return_value = low_conf_cands
        self.mock_rewriter.rewrite.return_value = RewriteResult(
            original_query="Query that times out",
            rewritten_query="Query that times out",
            success=False,
            fallback_used=True,
            latency_ms=10000.0,
            error_message="Gateway Timeout",
        )

        with patch.object(settings, "enable_adaptive_query_rewriting", True), \
             patch.object(settings, "enable_query_rewriting", False):
            resp = self.engine.query("Query that times out", stream=False)

            # Retriever called only once (did not attempt second pass with fallback query)
            self.mock_retriever.retrieve.assert_called_once_with("Query that times out", top_k=5)
            # Reranker received initial candidates
            self.mock_reranker.rerank.assert_called_once_with("Query that times out", low_conf_cands, top_n=3)
            self.assertEqual(resp.standalone_question, "Query that times out")

    def test_always_on_rewriting_precedence_over_adaptive(self):
        """When both enable_query_rewriting and enable_adaptive_query_rewriting are True, always-on takes precedence without two passes."""
        cands = [RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.80)]
        self.mock_retriever.retrieve.return_value = cands
        self.mock_rewriter.rewrite.return_value = RewriteResult(
            original_query="Original",
            rewritten_query="Always-on rewritten",
            success=True,
            fallback_used=False,
            latency_ms=200.0,
        )

        with patch.object(settings, "enable_query_rewriting", True), \
             patch.object(settings, "enable_adaptive_query_rewriting", True):
            resp = self.engine.query("Original", stream=False)

            # Rewriter called once
            self.mock_rewriter.rewrite.assert_called_once_with("Original")
            # Retriever called once with rewritten query
            self.mock_retriever.retrieve.assert_called_once_with("Always-on rewritten", top_k=5)


class TestConfidenceEvaluatorAllIssues(unittest.TestCase):
    """Exhaustive test suite verifying all 23 requirements for ConfidenceEvaluator."""

    def setUp(self):
        self.evaluator = ConfidenceEvaluator(
            score_threshold=0.725,
            mean_threshold=0.700,
            medium_score_threshold=0.680,
            medium_mean_threshold=0.660,
            medium_generic_top1=0.705,
            medium_generic_mean3=0.685,
            min_overlap=6,
            min_bm25=25.0,
            min_candidates=3,
        )

    # 1. High dense confidence
    def test_req1_high_dense_confidence(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.76),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.74),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.72),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "HIGH")
        self.assertEqual(res.action, "skip_rewrite")

    # 2. Low dense confidence
    def test_req2_low_dense_confidence(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.64),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.63),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.62),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertEqual(res.level, "LOW")
        self.assertEqual(res.action, "trigger_rewrite")

    # 3. Medium confidence
    def test_req3_medium_confidence(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.69),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.67),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.66),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertEqual(res.level, "MEDIUM")

    # 4. Top-1 passes but Mean-3 fails (steep drop)
    def test_req4_top1_passes_mean3_fails(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.74),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.66),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.65),
        ]
        res = self.evaluator.evaluate(cands)
        # Mean3 is (0.74 + 0.66 + 0.65)/3 = 0.6833 < 0.700 -> Not HIGH
        self.assertNotEqual(res.level, "HIGH")
        self.assertFalse(res.is_confident)

    # 5. Mean-3 passes but Top-1 fails (flat plateau under top-1 threshold)
    def test_req5_mean3_passes_top1_fails(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.71),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.705),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.70),
        ]
        res = self.evaluator.evaluate(cands)
        # Top1 0.71 < 0.725 -> Not HIGH
        self.assertNotEqual(res.level, "HIGH")

    # 6. Exact threshold boundary values
    def test_req6_exact_threshold_boundary_values(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.725),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.700),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.700),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "HIGH")

    # 7. RRF rank differs from dense similarity rank
    def test_req7_rrf_rank_differs_from_dense_similarity_rank(self):
        # RRF order has dense scores: 0.65, 0.76, 0.72
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.65, rrf_score=0.033),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.76, rrf_score=0.031),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.72, rrf_score=0.029),
        ]
        res = self.evaluator.evaluate(cands)
        # Top1 must be 0.76, NOT 0.65
        self.assertEqual(res.top1_score, 0.76)
        self.assertAlmostEqual(res.mean_top3_score, (0.76 + 0.72 + 0.65) / 3.0)

    # 8. Highest dense score is at RRF rank 3
    def test_req8_highest_dense_score_at_rrf_rank_3(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.60, rrf_score=0.033),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.62, rrf_score=0.030),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.85, rrf_score=0.028),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertEqual(res.top1_score, 0.85)

    # 9. Empty candidate pool
    def test_req9_empty_candidate_pool(self):
        res = self.evaluator.evaluate([])
        self.assertFalse(res.is_confident)
        self.assertEqual(res.level, "LOW")
        self.assertEqual(res.reason, "empty_candidates")

    # 10. Missing dense scores
    def test_req10_missing_dense_scores(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=None),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=None),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=None),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertEqual(res.level, "LOW")
        self.assertEqual(res.reason, "missing_or_invalid_scores")

    # 11. NaN and infinite scores
    def test_req11_nan_and_infinite_scores(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=float("nan")),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=float("inf")),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.75),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertEqual(res.reason, "missing_or_invalid_scores")

    # 12. Only one valid dense score
    def test_req12_only_one_valid_dense_score(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.78),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=None),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertEqual(res.top1_score, 0.78)
        self.assertIsNone(res.mean_top3_score)
        self.assertEqual(res.reason, "missing_or_invalid_scores")

    # 13. Only two valid dense scores
    def test_req13_only_two_valid_dense_scores(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.78),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.76),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertEqual(res.top1_score, 0.78)
        self.assertIsNone(res.mean_top3_score)

    # 14. BM25-only candidate
    def test_req14_bm25_only_candidate(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", bm25_score=28.5, score=28.5),
            RetrievedChunk(chunk_id="c2", text="t2", bm25_score=24.0, score=24.0),
            RetrievedChunk(chunk_id="c3", text="t3", bm25_score=20.0, score=20.0),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertFalse(res.is_confident)
        self.assertEqual(res.level, "LOW")

    # 15. Exact NIST document identifier match
    def test_req15_exact_nist_document_identifier_match(self):
        meta = ChunkMetadata(document_id="NIST SP 800-145", section="2.0")
        cands = [
            RetrievedChunk(chunk_id="c1", text="NIST SP 800-145 text", dense_score=0.70, bm25_score=35.0, metadata=meta),
            RetrievedChunk(chunk_id="c2", text="Text 2", dense_score=0.69, bm25_score=30.0),
            RetrievedChunk(chunk_id="c3", text="Text 3", dense_score=0.68, bm25_score=28.0),
        ]
        res = self.evaluator.evaluate(cands, query="What are the essential characteristics in NIST SP 800-145?")
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "MEDIUM")
        self.assertEqual(res.action, "skip_rewrite")
        self.assertIn("exact_identifier", res.reason)

    # 16. Exact NIST control identifier match
    def test_req16_exact_nist_control_identifier_match(self):
        cands = [
            RetrievedChunk(chunk_id="c1", text="Control AC-2 Account Management controls", dense_score=0.69, bm25_score=32.0),
            RetrievedChunk(chunk_id="c2", text="Account Management AC-2 requirements", dense_score=0.68, bm25_score=29.0),
            RetrievedChunk(chunk_id="c3", text="General text", dense_score=0.67, bm25_score=26.0),
        ]
        res = self.evaluator.evaluate(cands, query="What does security control AC-2 mandate?")
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "MEDIUM")
        self.assertEqual(res.action, "skip_rewrite")
        self.assertIn("exact_identifier", res.reason)

    # 17. Generic BM25 keyword match without exact identifier
    def test_req17_generic_bm25_keyword_match_without_exact_identifier(self):
        # Generic query with high BM25 on generic words but low dense evidence
        cands = [
            RetrievedChunk(chunk_id="c1", text="Cloud data security text", dense_score=0.67, bm25_score=35.0),
            RetrievedChunk(chunk_id="c2", text="Cloud storage implications", dense_score=0.66, bm25_score=30.0),
            RetrievedChunk(chunk_id="c3", text="Organizational data", dense_score=0.65, bm25_score=28.0),
        ]
        res = self.evaluator.evaluate(cands, query="What are the security implications of cloud data?")
        # Missing exact identifier and dense top1 < 0.680 -> triggers rewrite
        self.assertFalse(res.is_confident)
        self.assertEqual(res.action, "trigger_rewrite")

    # 18. Dense and BM25 candidate overlap
    def test_req18_dense_and_bm25_candidate_overlap(self):
        # 7 chunks have both dense and bm25 scores
        cands = [
            RetrievedChunk(chunk_id=f"c{i}", text=f"t{i}", dense_score=0.71 - i*0.005, bm25_score=28.0 - i)
            for i in range(7)
        ]
        res = self.evaluator.evaluate(cands, query="What are cloud incident response phases?")
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "MEDIUM")
        self.assertEqual(res.action, "skip_rewrite")
        self.assertIn("cross_modal_consensus", res.reason)

    # 19. No dense/BM25 overlap
    def test_req19_no_dense_bm25_overlap(self):
        # Candidates have dense_score but bm25_score is None (0 overlap)
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.69, bm25_score=None),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.68, bm25_score=None),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.67, bm25_score=None),
        ]
        res = self.evaluator.evaluate(cands, query="General security query")
        self.assertFalse(res.is_confident)
        self.assertEqual(res.action, "trigger_rewrite")
        self.assertIn("overlap=0<6", res.reason)

    # 20. Rewriter failure and timeout
    def test_req20_rewriter_failure_and_timeout(self):
        mock_retriever = MagicMock()
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = lambda q, cands, top_n: cands[:top_n]
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite.return_value = RewriteResult(
            original_query="Timeout Query",
            rewritten_query="Timeout Query",
            success=False,
            fallback_used=True,
            latency_ms=10000.0,
            error_message="Gateway Timeout",
        )
        engine = RAGEngine(
            retriever=mock_retriever,
            reranker=mock_reranker,
            retrieval_query_rewriter=mock_rewriter,
            confidence_evaluator=self.evaluator,
        )
        low_cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.60),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.59),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.58),
        ]
        mock_retriever.retrieve.return_value = low_cands
        with patch.object(settings, "enable_adaptive_query_rewriting", True):
            chunks, q = engine._retrieve_and_rank("Timeout Query")
            # Fallback preserved initial low_cands
            self.assertEqual([c.chunk_id for c in chunks], ["c1", "c2", "c3"])

    # 21. HIGH decision skips rewriting
    def test_req21_high_decision_skips_rewriting(self):
        mock_retriever = MagicMock()
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = lambda q, cands, top_n: cands[:top_n]
        mock_rewriter = MagicMock()
        engine = RAGEngine(
            retriever=mock_retriever,
            reranker=mock_reranker,
            retrieval_query_rewriter=mock_rewriter,
            confidence_evaluator=self.evaluator,
        )
        high_cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.76),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.74),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.72),
        ]
        mock_retriever.retrieve.return_value = high_cands
        with patch.object(settings, "enable_adaptive_query_rewriting", True):
            engine._retrieve_and_rank("High confidence question")
            mock_rewriter.rewrite.assert_not_called()

    # 22. LOW decision triggers rewriting
    def test_req22_low_decision_triggers_rewriting(self):
        mock_retriever = MagicMock()
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = lambda q, cands, top_n: cands[:top_n]
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite.return_value = RewriteResult(
            original_query="Low confidence question",
            rewritten_query="expanded search terms",
            success=True,
            fallback_used=False,
            latency_ms=150.0,
        )
        engine = RAGEngine(
            retriever=mock_retriever,
            reranker=mock_reranker,
            retrieval_query_rewriter=mock_rewriter,
            confidence_evaluator=self.evaluator,
        )
        low_cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.62),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.61),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.60),
        ]
        mock_retriever.retrieve.side_effect = [low_cands, [RetrievedChunk(chunk_id="c_rewr", text="rewr", dense_score=0.82)]]
        with patch.object(settings, "enable_adaptive_query_rewriting", True):
            engine._retrieve_and_rank("Low confidence question")
            mock_rewriter.rewrite.assert_called_once_with("Low confidence question")
            self.assertEqual(mock_retriever.retrieve.call_count, 2)

    # 23. MEDIUM decision follows the validated evidence policy
    def test_req23_medium_decision_follows_validated_policy(self):
        # Case A: Medium with exact identifier -> skips rewrite
        meta = ChunkMetadata(document_id="NIST SP 800-53")
        med_cands_ident = [
            RetrievedChunk(chunk_id="c1", text="SP 800-53 controls", dense_score=0.69, bm25_score=30.0, metadata=meta),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.68, bm25_score=28.0),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.67, bm25_score=26.0),
        ]
        res_ident = self.evaluator.evaluate(med_cands_ident, query="What controls are in NIST SP 800-53?")
        self.assertEqual(res_ident.level, "MEDIUM")
        self.assertTrue(res_ident.is_confident)
        self.assertEqual(res_ident.action, "skip_rewrite")

        # Case B: Medium without identifier and without overlap -> triggers rewrite
        med_cands_no_overlap = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.69, bm25_score=None),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.68, bm25_score=None),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.67, bm25_score=None),
        ]
        res_no_overlap = self.evaluator.evaluate(med_cands_no_overlap, query="General query")
        self.assertEqual(res_no_overlap.level, "MEDIUM")
        self.assertFalse(res_no_overlap.is_confident)
        self.assertEqual(res_no_overlap.action, "trigger_rewrite")



class TestConfidenceEvaluatorAuditFixes(unittest.TestCase):
    """Targeted unit tests for the four audit findings:
    1. Duplicate candidate handling.
    2. Identifier search depth configurability.
    3. Expanded identifier pattern coverage.
    4. Dictionary candidate compatibility.
    """

    def setUp(self):
        self.evaluator = ConfidenceEvaluator(
            score_threshold=0.725,
            mean_threshold=0.700,
            medium_score_threshold=0.680,
            medium_mean_threshold=0.660,
            min_candidates=3,
        )

    # -------------------------------------------------------------
    # 1. Duplicate candidate handling
    # -------------------------------------------------------------
    def test_duplicate_candidate_ids(self):
        """Duplicate chunks with identical ID should be deduplicated preserving order."""
        cands = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.75),
            RetrievedChunk(chunk_id="c1", text="text1 duplicate", dense_score=0.75),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.72),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.70),
        ]
        res = self.evaluator.evaluate(cands)
        # Unique count must be 3, not 4
        self.assertEqual(res.features["candidate_count"], 3)
        self.assertEqual(res.top1_score, 0.75)
        self.assertAlmostEqual(res.mean_top3_score, (0.75 + 0.72 + 0.70) / 3.0)

    def test_duplicate_candidates_with_different_scores(self):
        """Duplicate chunk_ids with different scores should retain the higher dense score."""
        cands = [
            RetrievedChunk(chunk_id="c1", text="low score c1", dense_score=0.65),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.71),
            RetrievedChunk(chunk_id="c1", text="high score c1", dense_score=0.78),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.70),
        ]
        res = self.evaluator.evaluate(cands)
        self.assertEqual(res.features["candidate_count"], 3)
        # c1 retained 0.78, so top1 must be 0.78
        self.assertEqual(res.top1_score, 0.78)
        self.assertAlmostEqual(res.mean_top3_score, (0.78 + 0.71 + 0.70) / 3.0)

    def test_duplicate_candidates_with_missing_ids(self):
        """Candidates with missing/empty chunk_id should be safely preserved as distinct instances."""
        cands = [
            RetrievedChunk(chunk_id="", text="empty id 1", dense_score=0.75),
            RetrievedChunk(chunk_id="", text="empty id 2", dense_score=0.72),
            RetrievedChunk(chunk_id="c1", text="valid id", dense_score=0.70),
        ]
        res = self.evaluator.evaluate(cands)
        # All 3 chunks preserved since empty IDs are treated as distinct instances
        self.assertEqual(res.features["candidate_count"], 3)
        self.assertEqual(res.top1_score, 0.75)
        self.assertAlmostEqual(res.mean_top3_score, (0.75 + 0.72 + 0.70) / 3.0)

    def test_verify_confidence_calculations_use_unique_chunks(self):
        """Duplicate chunks must not inflate pool size to meet min_candidates artificially."""
        # 3 candidate items, but only 2 unique chunk_ids
        cands = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.85),
            RetrievedChunk(chunk_id="c1", text="text1 duplicate", dense_score=0.85),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.75),
        ]
        res = self.evaluator.evaluate(cands)
        # With min_candidates=3, 2 unique chunks is insufficient -> triggers rewrite
        self.assertFalse(res.is_confident)
        self.assertEqual(res.reason, "missing_or_invalid_scores")
        self.assertEqual(res.features["candidate_count"], 2)

    # -------------------------------------------------------------
    # 2. Improve identifier search depth
    # -------------------------------------------------------------
    def test_identifier_at_rank_1(self):
        """Identifier at rank 1 is verified with default depth 5."""
        meta = ChunkMetadata(document_id="NIST SP 800-145")
        cands = [
            RetrievedChunk(chunk_id="c1", text="NIST SP 800-145 details", dense_score=0.70, bm25_score=30.0, metadata=meta),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.69, bm25_score=28.0),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.68, bm25_score=26.0),
        ]
        res = self.evaluator.evaluate(cands, query="Explain NIST SP 800-145 characteristics")
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "MEDIUM")
        self.assertIn("NIST SP 800-145", res.features["verified_identifiers"])

    def test_identifier_at_rank_5(self):
        """Identifier at rank 5 is verified within default depth 5."""
        cands = [
            RetrievedChunk(chunk_id=f"c{i}", text=f"general text {i}", dense_score=0.70, bm25_score=28.0)
            for i in range(1, 5)
        ]
        # Rank 5 contains the target
        meta = ChunkMetadata(document_id="NIST SP 800-145")
        cands.append(RetrievedChunk(chunk_id="c5", text="NIST SP 800-145 details", dense_score=0.69, bm25_score=32.0, metadata=meta))

        res = self.evaluator.evaluate(cands, query="Explain NIST SP 800-145 characteristics")
        self.assertTrue(res.is_confident)
        self.assertIn("NIST SP 800-145", res.features["verified_identifiers"])

    def test_identifier_at_rank_6_default_depth(self):
        """Identifier at rank 6 is NOT detected when depth is default 5."""
        cands = [
            RetrievedChunk(chunk_id=f"c{i}", text=f"general text {i}", dense_score=0.70, bm25_score=20.0)
            for i in range(1, 6)
        ]
        # Rank 6 contains the target
        meta = ChunkMetadata(document_id="NIST SP 800-145")
        cands.append(RetrievedChunk(chunk_id="c6", text="NIST SP 800-145 details", dense_score=0.69, bm25_score=32.0, metadata=meta))

        evaluator_default = ConfidenceEvaluator(identifier_search_depth=5, min_candidates=3)
        res = evaluator_default.evaluate(cands, query="Explain NIST SP 800-145 characteristics")
        # Identifier is outside depth 5 window -> not verified
        self.assertNotIn("NIST SP 800-145", res.features["verified_identifiers"])
        self.assertFalse(res.features["has_exact_match"])

    def test_identifier_outside_configured_depth(self):
        """When configured depth is 3, an identifier at rank 4 is not detected."""
        evaluator_depth3 = ConfidenceEvaluator(identifier_search_depth=3, min_candidates=3)
        meta = ChunkMetadata(document_id="NIST SP 800-145")
        cands = [
            RetrievedChunk(chunk_id="c1", text="t1", dense_score=0.70, bm25_score=20.0),
            RetrievedChunk(chunk_id="c2", text="t2", dense_score=0.69, bm25_score=20.0),
            RetrievedChunk(chunk_id="c3", text="t3", dense_score=0.68, bm25_score=20.0),
            RetrievedChunk(chunk_id="c4", text="NIST SP 800-145 details", dense_score=0.67, bm25_score=30.0, metadata=meta),
        ]
        res = evaluator_depth3.evaluate(cands, query="Explain NIST SP 800-145")
        self.assertFalse(res.features["has_exact_match"])

    def test_changing_identifier_search_depth_expands_detection(self):
        """Configuring depth=10 detects the identifier at rank 6."""
        evaluator_depth10 = ConfidenceEvaluator(identifier_search_depth=10, min_candidates=3)
        cands = [
            RetrievedChunk(chunk_id=f"c{i}", text=f"general text {i}", dense_score=0.70, bm25_score=28.0)
            for i in range(1, 6)
        ]
        meta = ChunkMetadata(document_id="NIST SP 800-145")
        cands.append(RetrievedChunk(chunk_id="c6", text="NIST SP 800-145 details", dense_score=0.69, bm25_score=32.0, metadata=meta))

        res = evaluator_depth10.evaluate(cands, query="Explain NIST SP 800-145 characteristics")
        self.assertTrue(res.is_confident)
        self.assertIn("NIST SP 800-145", res.features["verified_identifiers"])
        self.assertTrue(res.features["has_exact_match"])

    # -------------------------------------------------------------
    # 3. Expand identifier pattern coverage
    # -------------------------------------------------------------
    def test_valid_identifier_detection(self):
        """Verify new identifier patterns (NIST CSF, RMF, OWASP, CVE, CWE) are extracted."""
        from app.retrieval.confidence import extract_query_identifiers

        self.assertIn("NIST CSF", extract_query_identifiers("How does NIST CSF define functions?"))
        self.assertIn("CSF 2.0", extract_query_identifiers("What is new in CSF 2.0?"))
        self.assertIn("RMF", extract_query_identifiers("Explain the RMF steps."))
        self.assertIn("NIST RMF", extract_query_identifiers("What is the NIST RMF lifecycle?"))
        self.assertIn("OWASP", extract_query_identifiers("Follow OWASP guidelines for web apps."))
        self.assertIn("OWASP Top 10", extract_query_identifiers("Mitigate the OWASP Top 10 flaws."))
        self.assertIn("CVE-2024-1234", extract_query_identifiers("Is CVE-2024-1234 patched?"))
        self.assertIn("CWE-79", extract_query_identifiers("Remediate CWE-79 cross-site scripting."))
        self.assertIn("CWE 89", extract_query_identifiers("Prevent CWE 89 SQL injection."))

    def test_invalid_identifier_rejection(self):
        """Malformed or incomplete identifier strings should not match."""
        from app.retrieval.confidence import extract_query_identifiers

        self.assertEqual(extract_query_identifiers("CVE-12-34"), [])
        self.assertEqual(extract_query_identifiers("CVE-ABCD-1234"), [])
        self.assertEqual(extract_query_identifiers("CWE"), [])
        self.assertEqual(extract_query_identifiers("CWE-ABC"), [])

    def test_uppercase_and_lowercase_variations(self):
        """Case variations should be extracted consistently."""
        from app.retrieval.confidence import extract_query_identifiers

        self.assertEqual(extract_query_identifiers("cve-2024-5678"), ["cve-2024-5678"])
        self.assertEqual(extract_query_identifiers("cwe-79"), ["cwe-79"])
        self.assertEqual(extract_query_identifiers("owasp"), ["owasp"])
        self.assertEqual(extract_query_identifiers("rmf"), ["rmf"])
        self.assertEqual(extract_query_identifiers("csf"), ["csf"])
        self.assertEqual(extract_query_identifiers("ac-2"), ["ac-2"])

    def test_similar_text_that_should_not_match(self):
        """Partial substrings inside general words must not trigger false identifier extraction."""
        from app.retrieval.confidence import extract_query_identifiers

        self.assertEqual(extract_query_identifiers("This was harmful to the system"), [])
        self.assertEqual(extract_query_identifiers("We inspected csfr tokens"), [])
        self.assertEqual(extract_query_identifiers("The ac- generator was repaired"), [])

    def test_multiple_identifiers_in_one_query(self):
        """Multiple distinct identifiers in one query must all be preserved in order."""
        from app.retrieval.confidence import extract_query_identifiers

        query = "How does OWASP Top 10 mitigate CWE-79 and CVE-2024-1234 per NIST SP 800-53?"
        idents = extract_query_identifiers(query)
        self.assertIn("NIST SP 800-53", idents)
        self.assertIn("OWASP Top 10", idents)
        self.assertIn("CWE-79", idents)
        self.assertIn("CVE-2024-1234", idents)

    # -------------------------------------------------------------
    # 4. Fix dictionary candidate compatibility
    # -------------------------------------------------------------
    def test_dictionary_candidate_with_identifier_in_metadata(self):
        """Dictionary candidate with identifier in metadata dictionary is verified correctly."""
        from app.retrieval.confidence import verify_identifier_in_candidate

        candidate_dict = {
            "chunk_id": "c1",
            "text": "General cloud computing guidelines",
            "metadata": {
                "document_id": "NIST SP 800-145",
                "source_file": "NIST_SP_800-145.pdf",
                "section": "2.0 Definition",
            },
        }
        self.assertTrue(verify_identifier_in_candidate("NIST SP 800-145", candidate_dict))
        self.assertFalse(verify_identifier_in_candidate("NIST SP 800-53", candidate_dict))

    def test_dictionary_candidate_with_identifier_in_text(self):
        """Dictionary candidate with identifier in text is verified correctly."""
        from app.retrieval.confidence import verify_identifier_in_candidate

        candidate_dict = {
            "chunk_id": "c2",
            "text": "This policy addresses vulnerability remediation for CVE-2024-1234 across servers.",
            "metadata": {},
        }
        self.assertTrue(verify_identifier_in_candidate("CVE-2024-1234", candidate_dict))

    def test_dictionary_candidate_with_missing_metadata(self):
        """Dictionary candidate missing metadata or with None metadata does not crash."""
        from app.retrieval.confidence import verify_identifier_in_candidate

        candidate_dict = {"chunk_id": "c3", "text": "Some text without metadata"}
        self.assertFalse(verify_identifier_in_candidate("NIST SP 800-53", candidate_dict))

        candidate_dict_none = {"chunk_id": "c4", "metadata": None, "text": None}
        self.assertFalse(verify_identifier_in_candidate("NIST SP 800-53", candidate_dict_none))

    def test_domain_model_candidate_regression(self):
        """Domain model RetrievedChunk instances continue to be verified accurately."""
        from app.retrieval.confidence import verify_identifier_in_candidate

        meta = ChunkMetadata(document_id="NIST SP 800-53", section="AC-2")
        chunk = RetrievedChunk(chunk_id="chunk_001", text="Account Management controls", metadata=meta)
        self.assertTrue(verify_identifier_in_candidate("NIST SP 800-53", chunk))
        self.assertTrue(verify_identifier_in_candidate("AC-2", chunk))

    def test_evaluate_with_dictionary_candidates(self):
        """ConfidenceEvaluator.evaluate() successfully processes dictionary candidates end-to-end."""
        dict_cands = [
            {
                "chunk_id": "d1",
                "text": "NIST SP 800-145 essential characteristics",
                "dense_score": 0.70,
                "bm25_score": 30.0,
                "metadata": {"document_id": "NIST SP 800-145"},
            },
            {
                "chunk_id": "d2",
                "text": "Broad network access and resource pooling",
                "dense_score": 0.69,
                "bm25_score": 28.0,
                "metadata": {"document_id": "NIST SP 800-145"},
            },
            {
                "chunk_id": "d3",
                "text": "On-demand self-service",
                "dense_score": 0.68,
                "bm25_score": 26.0,
                "metadata": {"document_id": "NIST SP 800-145"},
            },
        ]
        res = self.evaluator.evaluate(dict_cands, query="What is in NIST SP 800-145?")
        self.assertTrue(res.is_confident)
        self.assertEqual(res.level, "MEDIUM")
        self.assertEqual(res.action, "skip_rewrite")
        self.assertIn("NIST SP 800-145", res.features["verified_identifiers"])


if __name__ == "__main__":
    unittest.main()
