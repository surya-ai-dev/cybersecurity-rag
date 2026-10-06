"""Application-level orchestrator for the Cybersecurity RAG system."""

from typing import Any, Callable, Iterator, List, Optional, Sequence, Union

from app.core.config import settings
from app.core.interfaces import (
    BaseConversationMemory,
    BaseLLMProvider,
    BaseReranker,
    BaseRetriever,
)
from app.core.models import Message, RAGResponse, RetrievedChunk
from app.conversation.conversation_memory import ConversationMemory
from app.conversation.query_rewriter import rewrite_question
from app.generation.build_context import build_context
from app.generation.providers.groq_provider import GroqProvider
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import CrossEncoderReranker


RAG_PROMPT_TEMPLATE = """You are a cybersecurity assistant for a Retrieval-Augmented
Generation (RAG) system.

Your task is to answer the user's question using ONLY the
retrieved context provided below.

IMPORTANT RULES:

1. Do not use information that is not supported by the context.
2. Do not invent facts.
3. If the context does not contain enough information, clearly
   say that the available context is insufficient.
4. Answer ONLY the user's question.
5. Do not provide additional background, related concepts,
   examples, characteristics, advantages, disadvantages, or
   recommendations unless they are directly required to answer
   the question.
6. Be concise. Use the minimum amount of information needed to
   completely answer the question.
7. If the question asks for a definition, give the definition
   and only the essential clarification.
8. If the question asks for specific points, provide only those
   points.
9. Do not turn a simple question into a detailed report.
10. Do not add a summary or "Key Points" section unless it is
    necessary to answer the question.
11. Do not use tables unless the user explicitly asks for one.
12. Every factual claim must be supported by the retrieved
    context and include [Source X].
13. Do not introduce information simply because it appears in
    the retrieved context.

USER QUESTION:
{question}

RETRIEVED CONTEXT:
{context}

Now provide the answer."""


class RAGEngine:
    """Orchestrates end-to-end question answering lifecycle using injected components."""

    def __init__(
        self,
        retriever: Optional[BaseRetriever] = None,
        reranker: Optional[BaseReranker] = None,
        query_rewriter: Optional[Callable[..., str]] = None,
        context_builder: Optional[Callable[[Sequence[Any]], str]] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        memory: Optional[BaseConversationMemory] = None,
        retrieval_top_k: Optional[int] = None,
        rerank_top_n: Optional[int] = None,
    ) -> None:
        """Initialize RAGEngine with injected component strategies.

        Args:
            retriever: Component implementing BaseRetriever (default: HybridRetriever).
            reranker: Component implementing BaseReranker (default: CrossEncoderReranker).
            query_rewriter: Function/callable for query rewriting (default: rewrite_question).
            context_builder: Function/callable for context formatting (default: build_context).
            llm_provider: Component implementing BaseLLMProvider (default: GroqProvider).
            memory: Component implementing BaseConversationMemory (default: ConversationMemory).
            retrieval_top_k: Candidate retrieval limit (default: 20).
            rerank_top_n: Reranked top document limit (default: 5).
        """
        self.retriever: BaseRetriever = retriever if retriever is not None else HybridRetriever()
        self.reranker: BaseReranker = reranker if reranker is not None else CrossEncoderReranker()
        self.query_rewriter: Callable[..., str] = query_rewriter if query_rewriter is not None else rewrite_question
        self.context_builder: Callable[[Sequence[Any]], str] = context_builder if context_builder is not None else build_context
        self.llm_provider: BaseLLMProvider = llm_provider if llm_provider is not None else GroqProvider()
        self.memory: BaseConversationMemory = memory if memory is not None else ConversationMemory()

        self.retrieval_top_k: int = retrieval_top_k or getattr(settings, "dense_top_k", 20)
        self.rerank_top_n: int = rerank_top_n or getattr(settings, "final_top_n", 5)

    def _rewrite_query(self, question: str, history: List[Union[Message, dict]]) -> str:
        """Rewrite question into standalone form using conversational history."""
        if not history:
            return question

        try:
            return self.query_rewriter(question, history, llm_provider=self.llm_provider)
        except TypeError:
            return self.query_rewriter(question, history)

    def _build_prompt(self, question: str, context: str) -> str:
        """Build grounded prompt formatted with standalone question and context blocks."""
        return RAG_PROMPT_TEMPLATE.format(question=question, context=context)

    def query(
        self,
        question: str,
        stream: bool = True,
    ) -> RAGResponse:
        """Execute the full RAG pipeline and return a structured RAGResponse domain object.

        Args:
            question: User cybersecurity question.
            stream: If True, streams tokens to stdout in real-time.

        Returns:
            RAGResponse object with question, standalone_question, answer, and sources.
        """
        # 1. Retrieve conversation history
        history = self.memory.get_messages()

        # 2. Rewrite query if needed
        standalone_question = self._rewrite_query(question, history)

        # 3. Hybrid candidate retrieval
        print("\n" + "=" * 70)
        print("STEP 1 — RETRIEVING DOCUMENTS")
        print("=" * 70)
        candidates = self.retriever.retrieve(
            standalone_question,
            top_k=self.retrieval_top_k,
        )
        print(f"\nRRF candidate documents: {len(candidates)}")

        # 4. Cross-encoder reranking
        print("\n" + "=" * 70)
        print("STEP 2 — RERANKING DOCUMENTS")
        print("=" * 70)
        reranked_chunks = self.reranker.rerank(
            standalone_question,
            candidates,
            top_n=self.rerank_top_n,
        )
        print(f"\nFinal reranked documents: {len(reranked_chunks)}")

        # 5. Build prompt context
        print("\n" + "=" * 70)
        print("STEP 3 — BUILDING CONTEXT")
        print("=" * 70)
        context = self.context_builder(reranked_chunks)
        print(f"Context built from {len(reranked_chunks)} chunks.")

        # 6. Generate answer
        print("\n" + "=" * 70)
        print("STEP 4 — GENERATING ANSWER")
        print("=" * 70)
        prompt = self._build_prompt(standalone_question, context)

        if stream:
            answer_parts = []
            for chunk in self.llm_provider.stream(
                prompt,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                print(chunk, end="", flush=True)
                answer_parts.append(chunk)
            answer = "".join(answer_parts)
        else:
            answer = self.llm_provider.generate(
                prompt,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )

        # 7. Record turn to memory
        self.memory.add_message(question, answer)

        return RAGResponse(
            question=question,
            standalone_question=standalone_question,
            answer=answer,
            sources=list(reranked_chunks),
        )

    def run(self, question: str, stream: bool = True) -> RAGResponse:
        """Alias for query() to provide simple intuitive interface."""
        return self.query(question, stream=stream)

    def stream(self, question: str) -> Iterator[str]:
        """Stream generated answer tokens while executing retrieval and memory updates.

        Yields:
            Token text chunks from the LLM provider.
        """
        history = self.memory.get_messages()
        standalone_question = self._rewrite_query(question, history)

        candidates = self.retriever.retrieve(standalone_question, top_k=self.retrieval_top_k)
        reranked_chunks = self.reranker.rerank(standalone_question, candidates, top_n=self.rerank_top_n)
        context = self.context_builder(reranked_chunks)
        prompt = self._build_prompt(standalone_question, context)

        full_answer = []
        try:
            for chunk in self.llm_provider.stream(
                prompt,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                full_answer.append(chunk)
                yield chunk
        finally:
            accumulated = "".join(full_answer)
            if accumulated:
                self.memory.add_message(question, accumulated)

    def close(self) -> None:
        """Cleanly release underlying retriever and reranker resources."""
        if hasattr(self.retriever, "close"):
            self.retriever.close()
        if hasattr(self.reranker, "close"):
            self.reranker.close()

    def __enter__(self) -> "RAGEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
