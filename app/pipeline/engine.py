"""Application-level orchestrator for the Cybersecurity RAG system."""

from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple, Union

from app.core.config import settings
from app.core.interfaces import (
    BaseConversationMemory,
    BaseLLMProvider,
    BaseMemoryManager,
    BaseReranker,
    BaseRetriever,
)
from app.core.models import MemoryContext, Message, RAGResponse, RetrievedChunk
from app.conversation.conversation_memory import ConversationMemory
from app.conversation.query_rewriter import rewrite_question
from app.generation.build_context import build_context
from app.generation.providers.groq_provider import GroqProvider
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.query_rewriter import QueryRewriter
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


def _is_memory_manager(memory: Any) -> bool:
    """Return True when memory implements BaseMemoryManager and is not an un-spec'd mock."""
    try:
        from unittest.mock import NonCallableMock

        if isinstance(memory, NonCallableMock) and getattr(memory, "_spec_class", None) is None:
            return False
    except Exception:
        pass
    return isinstance(memory, BaseMemoryManager)


def format_preference_instructions(preferences: Optional[Any]) -> str:
    """Format user presentation/focus preferences into grounded prompt instructions."""
    if preferences is None:
        return ""

    if isinstance(preferences, dict):
        detail = preferences.get("detail_level")
        fmt = preferences.get("response_format")
        lens = preferences.get("focus_lens")
        custom = preferences.get("custom_instructions")
    else:
        detail = getattr(preferences, "detail_level", None)
        fmt = getattr(preferences, "response_format", None)
        lens = getattr(preferences, "focus_lens", None)
        custom = getattr(preferences, "custom_instructions", None)

    detail_map = {
        "Concise": "Keep the answer concise, direct, and high-signal without filler.",
        "Balanced": "Provide a clear, balanced explanation with essential context and requirements.",
        "Deep Dive": "Provide a thorough deep dive covering control details, caveats, and nuances supported by the sources.",
    }
    format_map = {
        "Structured Bullets & Tables": "Organize using clean headings, structured bullets, and a concise Markdown table when comparing items.",
        "Step-by-Step": "Present requirements or guidance in a clear, numbered step-by-step sequence.",
        "TL;DR First": "Start with a brief 1-2 sentence TL;DR takeaway, followed by supporting evidence.",
    }
    lens_map = {
        "AI / Product Engineering": "Emphasize system architecture, product trade-offs, and integration reliability grounded in the retrieved context.",
        "Security & Compliance": "Emphasize NIST control objectives, risk posture, governance, and compliance assurance.",
        "Hands-On Code": "Emphasize actionable implementation specifics, configuration parameters, schemas, and verification checks from the retrieved context.",
    }

    lines: List[str] = []
    if detail:
        lines.append(f"- Detail Level ({detail}): {detail_map.get(detail, detail)}")
    if fmt:
        lines.append(f"- Response Format ({fmt}): {format_map.get(fmt, fmt)}")
    if lens:
        lines.append(f"- Focus Lens ({lens}): {lens_map.get(lens, lens)}")
    if custom and str(custom).strip():
        lines.append(f"- Additional User Note: {str(custom).strip()[:300]}")

    if not lines:
        return ""

    lines.append(
        "- Grounding Constraint: Strictly use only facts in RETRIEVED CONTEXT and cite every claim with [Source X]."
    )
    return "\n".join(lines)


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
        retrieval_query_rewriter: Optional[QueryRewriter] = None,
        confidence_evaluator: Optional[Any] = None,
        retrieval_top_k: Optional[int] = None,
        rerank_top_n: Optional[int] = None,
        enable_reranking: Optional[bool] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Initialize RAGEngine with injected component strategies.

        Args:
            retriever: Component implementing BaseRetriever (default: HybridRetriever).
            reranker: Component implementing BaseReranker (default: CrossEncoderReranker).
            query_rewriter: Function/callable for conversation rewriting (default: rewrite_question).
            context_builder: Function/callable for context formatting (default: build_context).
            llm_provider: Component implementing BaseLLMProvider (default: GroqProvider).
            memory: Component implementing BaseConversationMemory (default: MemoryManager when
                settings.enable_persistent_memory is True, else ConversationMemory).
            retrieval_query_rewriter: Component implementing QueryRewriter for search query optimization.
            confidence_evaluator: Component implementing ConfidenceEvaluator for adaptive rewriting decisions.
            retrieval_top_k: Candidate retrieval limit (default: 20).
            rerank_top_n: Reranked top document limit (default: 5).
            enable_reranking: Optional flag to toggle cross-encoder reranking (default: settings.enable_reranking).
            session_id: Optional session identifier used when persistent MemoryManager is active.
        """
        from app.retrieval.confidence import ConfidenceEvaluator

        self.retriever: BaseRetriever = retriever if retriever is not None else HybridRetriever()
        self.reranker: BaseReranker = reranker if reranker is not None else CrossEncoderReranker()
        self.query_rewriter: Callable[..., str] = query_rewriter if query_rewriter is not None else rewrite_question
        self.context_builder: Callable[[Sequence[Any]], str] = context_builder if context_builder is not None else build_context
        self.llm_provider: BaseLLMProvider = llm_provider if llm_provider is not None else GroqProvider()

        if memory is not None:
            self.memory: BaseConversationMemory = memory
        elif getattr(settings, "enable_persistent_memory", False):
            from app.conversation.memory_manager import MemoryManager

            self.memory = MemoryManager(
                session_id=session_id,
                llm_provider=self.llm_provider,
            )
        else:
            self.memory = ConversationMemory()
        rewriter_enabled = (
            getattr(settings, "enable_query_rewriting", False)
            or getattr(settings, "enable_adaptive_query_rewriting", False)
        )
        self.retrieval_query_rewriter: Optional[QueryRewriter] = (
            retrieval_query_rewriter
            if retrieval_query_rewriter is not None
            else QueryRewriter(enabled=rewriter_enabled)
        )
        self.confidence_evaluator: ConfidenceEvaluator = (
            confidence_evaluator
            if confidence_evaluator is not None
            else ConfidenceEvaluator()
        )

        self.retrieval_top_k: int = retrieval_top_k or getattr(settings, "dense_top_k", 20)
        self.rerank_top_n: int = rerank_top_n or getattr(settings, "final_top_n", 5)
        self.enable_reranking: bool = (
            enable_reranking
            if enable_reranking is not None
            else getattr(settings, "enable_reranking", True)
        )

    def _get_rewrite_context(self, question: str) -> Union[MemoryContext, List[Any]]:
        """Fetch MemoryContext from BaseMemoryManager or flat messages from BaseConversationMemory."""
        if _is_memory_manager(self.memory):
            return self.memory.get_context(question)  # type: ignore[union-attr]
        return self.memory.get_messages()

    def _record_turn(
        self,
        question: str,
        answer: str,
        standalone_question: str,
        final_chunks: Sequence[RetrievedChunk],
    ) -> None:
        """Persist turn metadata when using BaseMemoryManager, preserving 2-arg calls for mocks."""
        if _is_memory_manager(self.memory):
            self.memory.add_message(
                question,
                answer,
                standalone_question=standalone_question,  # type: ignore[call-arg]
                source_chunk_ids=[c.chunk_id for c in final_chunks],  # type: ignore[call-arg]
            )
        else:
            self.memory.add_message(question, answer)

    def _rewrite_query(
        self,
        question: str,
        history: Union[MemoryContext, Sequence[Union[Message, dict]]],
    ) -> str:
        """Rewrite question into standalone form using conversational context."""
        if isinstance(history, MemoryContext):
            if not history.has_context:
                return question
        elif not history:
            return question

        try:
            return self.query_rewriter(question, history, llm_provider=self.llm_provider)
        except TypeError:
            return self.query_rewriter(question, history)

    def _build_prompt(
        self,
        question: str,
        context: str,
        preferences: Optional[Any] = None,
    ) -> str:
        """Build grounded prompt formatted with standalone question, context, and user preferences."""
        prompt = RAG_PROMPT_TEMPLATE.format(question=question, context=context)
        pref_block = format_preference_instructions(preferences)
        if not pref_block:
            return prompt
        marker = "\nUSER QUESTION:\n"
        injection = f"\nUSER PREFERENCES (adapt presentation while staying strictly grounded):\n{pref_block}\n"
        if marker in prompt:
            return prompt.replace(marker, f"{injection}{marker}", 1)
        return f"{prompt}\n\n{injection}"

    def _retrieve_and_rank(
        self,
        standalone_question: str,
    ) -> Tuple[List[RetrievedChunk], str]:
        """Execute unified candidate retrieval, adaptive query rewriting, and optional reranking.

        Shared by query(), stream(), and run() to guarantee identical retrieval semantics.

        Args:
            standalone_question: Standalone disambiguated user query.

        Returns:
            Tuple of (final_ranked_chunks, effective_search_query).
        """
        search_query = standalone_question
        candidates = None

        always_on = getattr(settings, "enable_query_rewriting", False)
        adaptive_on = getattr(settings, "enable_adaptive_query_rewriting", False)

        if always_on and self.retrieval_query_rewriter is not None:
            if not getattr(self.retrieval_query_rewriter, "enabled", True):
                self.retrieval_query_rewriter.enabled = True
            rewrite_res = self.retrieval_query_rewriter.rewrite(standalone_question)
            if rewrite_res.success and not rewrite_res.fallback_used and rewrite_res.rewritten_query:
                search_query = rewrite_res.rewritten_query
            print("\n" + "=" * 70)
            print("STEP 1 — RETRIEVING DOCUMENTS (ALWAYS-ON REWRITE)")
            print("=" * 70)
            candidates = self.retriever.retrieve(
                search_query,
                top_k=self.retrieval_top_k,
            )
        elif adaptive_on and self.retrieval_query_rewriter is not None:
            from app.retrieval.confidence import merge_candidate_pools

            print("\n" + "=" * 70)
            print("STEP 1 — RETRIEVING DOCUMENTS (ADAPTIVE INITIAL PASS)")
            print("=" * 70)
            initial_candidates = self.retriever.retrieve(
                standalone_question,
                top_k=self.retrieval_top_k,
            )
            conf_res = self.confidence_evaluator.evaluate(initial_candidates, query=standalone_question)
            if conf_res.is_confident:
                candidates = initial_candidates
                search_query = standalone_question
                print(f"\n[Adaptive] Initial retrieval confident [Level: {getattr(conf_res, 'level', 'HIGH')}] ({conf_res.reason}). Skipping rewrite.")
            else:
                print(f"\n[Adaptive] Initial retrieval low/medium confidence [Level: {getattr(conf_res, 'level', 'LOW')}] ({conf_res.reason}). Triggering query rewrite...")
                if not getattr(self.retrieval_query_rewriter, "enabled", True):
                    self.retrieval_query_rewriter.enabled = True
                rewrite_res = self.retrieval_query_rewriter.rewrite(standalone_question)
                if rewrite_res.success and not rewrite_res.fallback_used and rewrite_res.rewritten_query:
                    search_query = rewrite_res.rewritten_query
                    print(f"[Adaptive] Second retrieval pass using rewritten query: {search_query[:75]}...")
                    rewritten_candidates = self.retriever.retrieve(
                        search_query,
                        top_k=self.retrieval_top_k,
                    )
                    candidates = merge_candidate_pools(
                        initial_candidates,
                        rewritten_candidates,
                        limit=self.retrieval_top_k,
                    )
                else:
                    print("[Adaptive] Rewriter fallback used; retaining initial candidates.")
                    candidates = initial_candidates
                    search_query = standalone_question
        else:
            print("\n" + "=" * 70)
            print("STEP 1 — RETRIEVING DOCUMENTS")
            print("=" * 70)
            candidates = self.retriever.retrieve(
                search_query,
                top_k=self.retrieval_top_k,
            )
        print(f"\nRetrieved candidate documents: {len(candidates)}")

        # Step 2: Cross-encoder reranking (optional)
        if self.enable_reranking:
            print("\n" + "=" * 70)
            print("STEP 2 — RERANKING DOCUMENTS")
            print("=" * 70)
            final_chunks = self.reranker.rerank(
                standalone_question,
                candidates,
                top_n=self.rerank_top_n,
            )
            print(f"\nFinal reranked documents: {len(final_chunks)}")
        else:
            print("\n" + "=" * 70)
            print("STEP 2 — RERANKING BYPASSED (DISABLED)")
            print("=" * 70)
            final_chunks = list(candidates)[:self.rerank_top_n]
            print(f"\nFinal top documents: {len(final_chunks)}")

        return final_chunks, search_query

    def query(
        self,
        question: str,
        stream: bool = True,
        preferences: Optional[Any] = None,
    ) -> RAGResponse:
        """Execute the full RAG pipeline and return a structured RAGResponse domain object.

        Args:
            question: User cybersecurity question.
            stream: If True, streams tokens to stdout in real-time.

        Returns:
            RAGResponse object with question, standalone_question, answer, and sources.
        """
        # 1. Retrieve conversation history / structured memory context
        history = self._get_rewrite_context(question)

        # 2. Rewrite query if needed
        standalone_question = self._rewrite_query(question, history)

        # 3. Retrieve candidates, adaptively rewrite, and rerank
        final_chunks, search_query = self._retrieve_and_rank(standalone_question)

        # 4. Build prompt context
        print("\n" + "=" * 70)
        print("STEP 3 — BUILDING CONTEXT")
        print("=" * 70)
        context = self.context_builder(final_chunks)
        print(f"Context built from {len(final_chunks)} chunks.")

        # 5. Generate answer
        print("\n" + "=" * 70)
        print("STEP 4 — GENERATING ANSWER")
        print("=" * 70)
        prompt = self._build_prompt(standalone_question, context, preferences=preferences)

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

        # 6. Record turn to memory
        self._record_turn(question, answer, standalone_question, final_chunks)

        return RAGResponse(
            question=question,
            standalone_question=standalone_question,
            answer=answer,
            sources=list(final_chunks),
        )

    def run(self, question: str, stream: bool = True) -> RAGResponse:
        """Alias for query() to provide simple intuitive interface."""
        return self.query(question, stream=stream)

    def stream(
        self,
        question: str,
        preferences: Optional[Any] = None,
    ) -> Iterator[str]:
        """Stream generated answer tokens while executing retrieval and memory updates.

        Yields:
            Token text chunks from the LLM provider.
        """
        history = self._get_rewrite_context(question)
        standalone_question = self._rewrite_query(question, history)

        final_chunks, search_query = self._retrieve_and_rank(standalone_question)
        context = self.context_builder(final_chunks)
        prompt = self._build_prompt(standalone_question, context, preferences=preferences)

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
                self._record_turn(question, accumulated, standalone_question, final_chunks)

    def close(self) -> None:
        """Cleanly release underlying retriever, reranker, and memory resources."""
        if hasattr(self.retriever, "close"):
            self.retriever.close()
        if hasattr(self.reranker, "close"):
            self.reranker.close()
        if hasattr(self.memory, "close"):
            self.memory.close()

    def __enter__(self) -> "RAGEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
