"""Regression and unit test suite for the modular Cybersecurity RAG architecture."""

import unittest
from typing import Any, List, Sequence

from app.core.config import settings
from app.core.interfaces import (
    BaseConversationMemory,
    BaseLLMProvider,
    BaseReranker,
    BaseRetriever,
)
from app.core.models import ChunkMetadata, Message, RAGResponse, RetrievedChunk
from app.conversation.conversation_memory import ConversationMemory
from app.conversation.query_rewriter import rewrite_question
from app.generation.build_context import build_context
from app.generation.providers.groq_provider import GroqProvider
from app.retrieval.dense import DenseRetriever
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.rrf import RRFFusion
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import CrossEncoderReranker
from app.pipeline.engine import RAGEngine


class TestDomainModels(unittest.TestCase):
    """Test domain data models and backward compatibility."""

    def test_chunk_metadata(self):
        meta = ChunkMetadata(
            document_id="NIST_SP_800-53",
            category="guidelines",
            source_file="sp800-53.pdf",
            section="AC-6",
            token_count=150,
            extra={"custom": 123},
        )
        self.assertEqual(meta["document_id"], "NIST_SP_800-53")
        self.assertEqual(meta.get("section"), "AC-6")
        self.assertEqual(meta["custom"], 123)
        as_dict = meta.to_dict()
        self.assertEqual(as_dict["document_id"], "NIST_SP_800-53")

    def test_retrieved_chunk(self):
        chunk = RetrievedChunk(
            chunk_id="chunk_001",
            text="Least privilege principle",
            metadata=ChunkMetadata(document_id="NIST_SP_800-53"),
            score=0.95,
            dense_score=0.88,
            bm25_score=12.5,
            rrf_score=0.032,
            reranker_score=4.5,
        )
        self.assertEqual(chunk["chunk_id"], "chunk_001")
        self.assertEqual(chunk["score"], 0.95)
        self.assertEqual(chunk.get("rrf_score"), 0.032)
        chunk_dict = chunk.to_dict()
        self.assertEqual(chunk_dict["chunk_id"], "chunk_001")

    def test_message_and_rag_response(self):
        msg = Message(user="hello", assistant="hi")
        self.assertEqual(msg["user"], "hello")
        self.assertEqual(msg.get("assistant"), "hi")

        resp = RAGResponse(
            question="What is X?",
            standalone_question="What is X?",
            answer="X is Y [Source 1].",
            sources=[RetrievedChunk(chunk_id="c1", text="X is Y")],
        )
        self.assertEqual(len(resp.sources), 1)
        self.assertIn("c1", resp.to_dict()["sources"][0]["chunk_id"])


class TestInterfaceCompliance(unittest.TestCase):
    """Verify that all concrete components implement their respective protocols."""

    def test_retrieval_interfaces(self):
        self.assertTrue(issubclass(DenseRetriever, BaseRetriever))
        self.assertTrue(issubclass(BM25Retriever, BaseRetriever))
        self.assertTrue(issubclass(HybridRetriever, BaseRetriever))

    def test_reranker_interface(self):
        self.assertTrue(issubclass(CrossEncoderReranker, BaseReranker))

    def test_llm_provider_interface(self):
        self.assertTrue(issubclass(GroqProvider, BaseLLMProvider))

    def test_memory_interface(self):
        self.assertTrue(issubclass(ConversationMemory, BaseConversationMemory))


class TestMemoryAndContextBuilder(unittest.TestCase):
    """Test conversation memory and pure context builder."""

    def test_conversation_memory(self):
        mem = ConversationMemory(max_recent_messages=2)
        mem.add_message("Q1", "A1")
        mem.add_message("Q2", "A2")
        mem.add_message("Q3", "A3")
        messages = mem.get_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["user"], "Q2")
        self.assertEqual(messages[1]["user"], "Q3")

    def test_pure_context_builder(self):
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                text="Content 1",
                metadata=ChunkMetadata(document_id="DOC1", section="SEC1"),
            ),
            RetrievedChunk(
                chunk_id="c2",
                text="Content 2",
                metadata=ChunkMetadata(document_id="DOC2", section="SEC2"),
            ),
        ]
        context = build_context(chunks)
        self.assertIn("SOURCE 1", context)
        self.assertIn("Document: DOC1", context)
        self.assertIn("Content 1", context)
        self.assertIn("SOURCE 2", context)
        self.assertIn("Document: DOC2", context)
        self.assertIn("Content 2", context)


class MockRetriever(BaseRetriever):
    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id="mock_chunk_1",
                text="Least privilege restricts access to the minimum necessary.",
                metadata=ChunkMetadata(document_id="NIST_TEST"),
            )
        ]


class MockReranker(BaseReranker):
    def rerank(self, query: str, chunks: Sequence[Any], top_n: int = 5) -> List[RetrievedChunk]:
        return list(chunks)[:top_n]


class MockLLMProvider(BaseLLMProvider):
    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 512) -> str:
        return "Least privilege is access limitation. [Source 1]"

    def stream(self, prompt: str, temperature: float = 0.0, max_tokens: int = 512):
        yield "Least privilege is access limitation. [Source 1]"


class TestRAGEngineOrchestration(unittest.TestCase):
    """Test RAGEngine dependency injection and query execution."""

    def test_rag_engine_with_mocks(self):
        engine = RAGEngine(
            retriever=MockRetriever(),
            reranker=MockReranker(),
            llm_provider=MockLLMProvider(),
            memory=ConversationMemory(),
        )

        resp = engine.query("What is least privilege?", stream=False)
        self.assertIsInstance(resp, RAGResponse)
        self.assertEqual(resp.question, "What is least privilege?")
        self.assertIn("[Source 1]", resp.answer)
        self.assertEqual(len(resp.sources), 1)
        self.assertEqual(resp.sources[0].chunk_id, "mock_chunk_1")

        # Test memory recording
        history = engine.memory.get_messages()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["user"], "What is least privilege?")


if __name__ == "__main__":
    unittest.main()
