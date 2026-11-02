"""Integration tests for the unified Cybersecurity RAG pipeline.

Tests:
1. Reranking toggle (enable_reranking=True vs enable_reranking=False).
2. Streaming candidate retrieval and adaptive rewriting unification.
3. Dynamic score label formatting in build_context.
4. Confidence evaluation safe fallback when dense scores are unavailable.
5. End-to-end integration with mock components.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.core.models import ChunkMetadata, RetrievedChunk, RAGResponse
from app.generation.build_context import build_context
from app.pipeline.engine import RAGEngine
from app.retrieval.confidence import ConfidenceEvaluator, extract_dense_score


class TestPipelineRerankToggle(unittest.TestCase):
    """Verify that enable_reranking configures cross-encoder invocation correctly."""

    def setUp(self):
        self.mock_retriever = MagicMock()
        self.mock_retriever.retrieve.return_value = [
            RetrievedChunk(chunk_id=f"chunk_{i}", text=f"Text {i}", dense_score=0.70 + i * 0.02)
            for i in range(10)
        ]
        self.mock_reranker = MagicMock()
        self.mock_reranker.rerank.side_effect = lambda q, docs, top_n: [
            RetrievedChunk(chunk_id=c.chunk_id, text=c.text, reranker_score=5.0 - idx)
            for idx, c in enumerate(docs[:top_n])
        ]
        self.mock_llm = MagicMock()
        self.mock_llm.generate.return_value = "Answer [Source 1]"
        self.mock_llm.stream.return_value = ["Answer ", "[Source 1]"]
        self.mock_memory = MagicMock()
        self.mock_memory.get_messages.return_value = []

    def test_reranking_enabled_by_default(self):
        """When enable_reranking is True, reranker.rerank must be called."""
        engine = RAGEngine(
            retriever=self.mock_retriever,
            reranker=self.mock_reranker,
            llm_provider=self.mock_llm,
            memory=self.mock_memory,
            enable_reranking=True,
            rerank_top_n=3,
        )
        resp = engine.query("What is access control?", stream=False)
        self.mock_reranker.rerank.assert_called_once()
        self.assertEqual(len(resp.sources), 3)
        self.assertIsNotNone(resp.sources[0].reranker_score)

    def test_reranking_disabled_bypasses_cross_encoder(self):
        """When enable_reranking is False, reranker.rerank must NOT be called."""
        engine = RAGEngine(
            retriever=self.mock_retriever,
            reranker=self.mock_reranker,
            llm_provider=self.mock_llm,
            memory=self.mock_memory,
            enable_reranking=False,
            rerank_top_n=4,
        )
        resp = engine.query("What is access control?", stream=False)
        self.mock_reranker.rerank.assert_not_called()
        self.assertEqual(len(resp.sources), 4)
        self.assertEqual(resp.sources[0].chunk_id, "chunk_0")


class TestStreamAndQueryUnifiedFlow(unittest.TestCase):
    """Verify stream() and query() share candidate retrieval and rewriting."""

    def setUp(self):
        self.mock_retriever = MagicMock()
        self.mock_retriever.retrieve.return_value = [
            RetrievedChunk(chunk_id="c1", text="text1", dense_score=0.80),
            RetrievedChunk(chunk_id="c2", text="text2", dense_score=0.75),
            RetrievedChunk(chunk_id="c3", text="text3", dense_score=0.72),
        ]
        self.mock_reranker = MagicMock()
        self.mock_reranker.rerank.side_effect = lambda q, docs, top_n: docs[:top_n]
        self.mock_llm = MagicMock()
        self.mock_llm.generate.return_value = "Answer [Source 1]"
        self.mock_llm.stream.return_value = iter(["Streaming ", "tokens..."])
        self.mock_memory = MagicMock()
        self.mock_memory.get_messages.return_value = []

    def test_stream_executes_unified_retrieval(self):
        """stream() must retrieve candidates, rerank, build context, and record memory."""
        engine = RAGEngine(
            retriever=self.mock_retriever,
            reranker=self.mock_reranker,
            llm_provider=self.mock_llm,
            memory=self.mock_memory,
            enable_reranking=True,
            rerank_top_n=3,
        )
        tokens = list(engine.stream("What is zero trust?"))
        self.assertEqual("".join(tokens), "Streaming tokens...")
        self.mock_retriever.retrieve.assert_called_once()
        self.mock_reranker.rerank.assert_called_once()
        self.mock_memory.add_message.assert_called_once_with("What is zero trust?", "Streaming tokens...")


class TestDynamicContextScoreLabels(unittest.TestCase):
    """Verify build_context displays appropriate labels for each scoring stage."""

    def test_reranker_score_label(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Reranked content",
            reranker_score=4.1234,
            dense_score=0.81,
            rrf_score=0.032,
            metadata=ChunkMetadata(document_id="DOC_1", section="SEC_1"),
        )
        ctx = build_context([chunk])
        self.assertIn("Reranker Score: 4.1234", ctx)
        self.assertNotIn("RRF Score: 0.000000", ctx)

    def test_rrf_score_label(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Fused content",
            rrf_score=0.032258,
            dense_score=0.75,
            metadata=ChunkMetadata(document_id="DOC_1", section="SEC_1"),
        )
        ctx = build_context([chunk])
        self.assertIn("RRF Score: 0.032258", ctx)

    def test_dense_score_label(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="Dense content",
            dense_score=0.7845,
            metadata=ChunkMetadata(document_id="DOC_1", section="SEC_1"),
        )
        ctx = build_context([chunk])
        self.assertIn("Dense Score: 0.7845", ctx)

    def test_bm25_score_label(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="BM25 content",
            bm25_score=15.4321,
            metadata=ChunkMetadata(document_id="DOC_1", section="SEC_1"),
        )
        ctx = build_context([chunk])
        self.assertIn("BM25 Score: 15.4321", ctx)


class TestSafeConfidenceScoreExtraction(unittest.TestCase):
    """Verify extract_dense_score never confuses RRF or BM25 scores with dense similarity."""

    def test_extract_dense_score_with_explicit_dense_score(self):
        chunk = RetrievedChunk(chunk_id="c1", text="t", dense_score=0.765)
        self.assertEqual(extract_dense_score(chunk), 0.765)

    def test_extract_dense_score_ignores_rrf_score(self):
        chunk = RetrievedChunk(chunk_id="c1", text="t", score=0.01639, rrf_score=0.01639)
        self.assertIsNone(extract_dense_score(chunk))

    def test_extract_dense_score_ignores_bm25_score(self):
        chunk = RetrievedChunk(chunk_id="c1", text="t", score=12.5, bm25_score=12.5)
        self.assertIsNone(extract_dense_score(chunk))

    def test_extract_dense_score_ignores_reranker_score(self):
        chunk = RetrievedChunk(chunk_id="c1", text="t", score=3.2, reranker_score=3.2)
        self.assertIsNone(extract_dense_score(chunk))


if __name__ == "__main__":
    unittest.main()
