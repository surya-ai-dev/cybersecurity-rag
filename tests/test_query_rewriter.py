"""Unit and integration tests for LLM-based Query Rewriting in Cybersecurity RAG."""

import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.core.models import Message, RAGResponse, RetrievedChunk
from app.pipeline.engine import RAGEngine
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.query_rewriter import (
    QUERY_REWRITE_SYSTEM_PROMPT,
    QueryRewriter,
    RewriteResult,
    rewrite_query,
)


class TestQueryRewriter(unittest.TestCase):
    """Unit tests for QueryRewriter class with mocked LLM providers."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.rewriter = QueryRewriter(
            client=self.mock_client,
            model_name="qwen/qwen3.8-27b",
            enabled=True,
            timeout=5.0,
            max_retries=2,
            max_tokens=256,
        )

    def test_rewrite_representative_question_success(self):
        """Test successful query rewriting of a representative cybersecurity question."""
        original_q = "What challenges can organizations face when monitoring security in public cloud environments?"
        mock_output = (
            "public cloud security monitoring challenges event logs provider controls incident detection forensics"
        )

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content=mock_output))]
        self.mock_client.chat.completions.create.return_value = mock_completion

        res = self.rewriter.rewrite(original_q)

        self.assertTrue(res.success)
        self.assertFalse(res.fallback_used)
        self.assertEqual(res.original_query, original_q)
        self.assertEqual(res.rewritten_query, mock_output)
        self.assertEqual(res.model_used, "qwen/qwen3.8-27b")
        self.assertGreater(res.latency_ms, 0.0)

        # Verify call arguments
        self.mock_client.chat.completions.create.assert_called_once()
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "qwen/qwen3.8-27b")
        self.assertEqual(call_kwargs["temperature"], 0.0)
        self.assertEqual(call_kwargs["max_completion_tokens"], 256)
        messages = call_kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("cybersecurity document search query optimizer", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn(original_q, messages[1]["content"])

    def test_preservation_of_nist_identifiers_and_acronyms(self):
        """Verify prompt constraints require preserving NIST standards and acronyms."""
        self.assertIn("NIST SP 800-145", QUERY_REWRITE_SYSTEM_PROMPT)
        self.assertIn("NIST SP 800-218", QUERY_REWRITE_SYSTEM_PROMPT)
        self.assertIn("SSDF", QUERY_REWRITE_SYSTEM_PROMPT)
        self.assertIn("PO", QUERY_REWRITE_SYSTEM_PROMPT)
        self.assertIn("PS", QUERY_REWRITE_SYSTEM_PROMPT)
        self.assertIn("PW", QUERY_REWRITE_SYSTEM_PROMPT)
        self.assertIn("RV", QUERY_REWRITE_SYSTEM_PROMPT)

        question = "What are the core practice groups of NIST SP 800-218 SSDF?"
        expected_rewrite = "NIST SP 800-218 SSDF core practice groups Prepare the Organization PO Protect Software PS Produce Well-Secured Software PW Respond to Vulnerabilities RV"

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content=f'"{expected_rewrite}"'))]
        self.mock_client.chat.completions.create.return_value = mock_completion

        res = self.rewriter.rewrite(question)
        self.assertTrue(res.success)
        self.assertEqual(res.rewritten_query, expected_rewrite)
        self.assertIn("NIST SP 800-218", res.rewritten_query)
        self.assertIn("SSDF", res.rewritten_query)
        self.assertIn("PO", res.rewritten_query)

    def test_rejection_of_empty_whitespace_malformed_output(self):
        """Rejection of empty or whitespace-only model outputs with safe fallback."""
        test_cases = ["", "   \n\t  ", "AB"]  # Empty, whitespace, or < 3 chars

        for malformed in test_cases:
            self.mock_client.reset_mock()
            mock_completion = MagicMock()
            mock_completion.choices = [MagicMock(message=MagicMock(content=malformed))]
            self.mock_client.chat.completions.create.return_value = mock_completion

            res = self.rewriter.rewrite("How does multi-tenancy affect cloud isolation?")
            self.assertFalse(res.success)
            self.assertTrue(res.fallback_used)
            self.assertEqual(res.rewritten_query, "How does multi-tenancy affect cloud isolation?")
            self.assertIn("Empty or malformed", str(res.error_message))
            # Verify retry count: 1 initial attempt + 2 retries = 3 calls
            self.assertEqual(self.mock_client.chat.completions.create.call_count, 3)

    def test_provider_error_and_timeout_with_bounded_retries(self):
        """Verify provider exceptions trigger bounded retries and graceful fallback."""
        self.mock_client.chat.completions.create.side_effect = TimeoutError("Request timed out to Groq")

        res = self.rewriter.rewrite("What is measured service in cloud computing?")

        self.assertFalse(res.success)
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.rewritten_query, "What is measured service in cloud computing?")
        self.assertIn("Request timed out", str(res.error_message))
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 3)

    def test_disabled_rewriting_flag_preserves_query_without_api_call(self):
        """When enabled=False, rewriter directly returns original query without invoking client."""
        disabled_rewriter = QueryRewriter(
            client=self.mock_client,
            enabled=False,
        )

        res = disabled_rewriter.rewrite("What is NIST SP 800-53 control AC-2?")

        self.assertTrue(res.success)
        self.assertFalse(res.fallback_used)
        self.assertEqual(res.rewritten_query, "What is NIST SP 800-53 control AC-2?")
        self.mock_client.chat.completions.create.assert_not_called()

    def test_convenience_rewrite_query_function(self):
        """Test convenience helper rewrite_query()."""
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="optimized search query"))]
        self.mock_client.chat.completions.create.return_value = mock_completion

        res_str = rewrite_query("Original query", rewriter=self.rewriter)
        self.assertEqual(res_str, "optimized search query")


class TestRetrievalRouting(unittest.TestCase):
    """Test routing of rewritten query into retrievers."""

    @patch("app.retrieval.retriever.get_default_retriever")
    def test_dense_retrieve_routes_rewritten_query(self, mock_get_retriever):
        """Verify dense_retrieve() uses rewritten query when feature flag is enabled."""
        from app.retrieval.retriever import dense_retrieve

        mock_hybrid = MagicMock()
        mock_get_retriever.return_value = mock_hybrid

        with patch.object(settings, "enable_query_rewriting", True):
            with patch("app.retrieval.query_rewriter.rewrite_query", return_value="rewritten dense query"):
                dense_retrieve("original user question", top_k=10)

                mock_hybrid.dense_retriever.retrieve.assert_called_once_with(
                    "rewritten dense query",
                    top_k=10,
                )

    @patch("app.retrieval.retriever.get_default_retriever")
    def test_hybrid_retrieve_routes_rewritten_query(self, mock_get_retriever):
        """Verify retrieve() routes rewritten query to hybrid retrieval."""
        from app.retrieval.retriever import retrieve

        mock_hybrid = MagicMock()
        mock_get_retriever.return_value = mock_hybrid

        with patch.object(settings, "enable_query_rewriting", True):
            with patch("app.retrieval.query_rewriter.rewrite_query", return_value="rewritten hybrid query"):
                retrieve("original user question", top_k=20)

                mock_hybrid.retrieve.assert_called_once_with(
                    "rewritten hybrid query",
                    top_k=20,
                )


class TestRAGEngineIntegration(unittest.TestCase):
    """Integration test verifying RAGEngine separates retrieval search query from generation prompt."""

    def test_rag_engine_optimizes_retrieval_while_retaining_prompt_and_memory(self):
        """Verify RAGEngine uses rewritten query for retrieval expansion but retains standalone question for reranker, prompt, and memory."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            RetrievedChunk(chunk_id="chunk_1", text="Relevant cybersecurity text", dense_score=0.9)
        ]

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [
            RetrievedChunk(chunk_id="chunk_1", text="Relevant cybersecurity text", reranker_score=0.95)
        ]

        mock_llm_provider = MagicMock()
        mock_llm_provider.generate.return_value = "Detailed cybersecurity answer grounded in evidence."

        mock_memory = MagicMock()
        mock_memory.get_messages.return_value = []

        mock_query_rewriter = MagicMock()
        mock_query_rewriter.rewrite.return_value = RewriteResult(
            original_query="What are cloud security challenges?",
            rewritten_query="public cloud security monitoring challenges event logs provider controls",
            success=True,
            fallback_used=False,
            latency_ms=45.0,
        )

        engine = RAGEngine(
            retriever=mock_retriever,
            reranker=mock_reranker,
            llm_provider=mock_llm_provider,
            memory=mock_memory,
            retrieval_query_rewriter=mock_query_rewriter,
            retrieval_top_k=20,
            rerank_top_n=5,
        )

        with patch.object(settings, "enable_query_rewriting", True):
            resp = engine.query("What are cloud security challenges?", stream=False)

            # 1. Verification of QueryRewriter call
            mock_query_rewriter.rewrite.assert_called_once_with("What are cloud security challenges?")

            # 2. Retriever received optimized search query; Reranker received original standalone question
            mock_retriever.retrieve.assert_called_once_with(
                "public cloud security monitoring challenges event logs provider controls",
                top_k=20,
            )
            mock_reranker.rerank.assert_called_once_with(
                "What are cloud security challenges?",
                mock_retriever.retrieve.return_value,
                top_n=5,
            )

            # 3. LLM generation prompt was formatted with standalone question, NOT the search query
            mock_llm_provider.generate.assert_called_once()
            prompt_sent = mock_llm_provider.generate.call_args[0][0]
            self.assertIn("USER QUESTION:\nWhat are cloud security challenges?", prompt_sent)
            self.assertNotIn("public cloud security monitoring challenges", prompt_sent)

            # 4. Memory received original user question and generated answer
            mock_memory.add_message.assert_called_once_with(
                "What are cloud security challenges?",
                "Detailed cybersecurity answer grounded in evidence.",
            )

            # 5. Response object preserves standalone_question and question
            self.assertEqual(resp.question, "What are cloud security challenges?")
            self.assertEqual(resp.standalone_question, "What are cloud security challenges?")
            self.assertEqual(resp.answer, "Detailed cybersecurity answer grounded in evidence.")
            self.assertEqual(len(resp.sources), 1)


if __name__ == "__main__":
    unittest.main()
