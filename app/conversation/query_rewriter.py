"""Query rewriter for conversational cybersecurity RAG."""

import logging
from typing import List, Optional, Sequence, Union

from app.core.config import settings
from app.core.interfaces import BaseLLMProvider
from app.core.models import MemoryContext, Message
from app.generation.providers.groq_provider import GroqProvider

logger = logging.getLogger(__name__)

# Model configuration
GROQ_MODEL = settings.llm_model

# Provider instance conforming to BaseLLMProvider
provider: BaseLLMProvider = GroqProvider()


def _format_turns_block(messages: Sequence[Union[Message, dict]]) -> str:
    """Render Message or dict turns cleanly for the disambiguation prompt."""
    blocks: List[str] = []
    for message in messages:
        if isinstance(message, dict):
            user_msg = message.get("user", "")
            assistant_msg = message.get("assistant", "")
        else:
            user_msg = getattr(message, "user", "")
            assistant_msg = getattr(message, "assistant", "")
        blocks.append(f"User: {user_msg}\nAssistant: {assistant_msg}")
    return "\n\n".join(blocks)


def _format_memory_context_block(ctx: MemoryContext) -> str:
    """Format three-tier MemoryContext sections, omitting empty tiers."""
    sections: List[str] = []

    if ctx.summary and ctx.summary.strip():
        sections.append(f"Session Summary:\n{ctx.summary.strip()}")

    if ctx.active_facts:
        fact_lines = [
            f"- [{fact.category}] {fact.key}: {fact.value}"
            for fact in ctx.active_facts
        ]
        sections.append("Active Technical Context / Standards:\n" + "\n".join(fact_lines))

    if ctx.recent_messages:
        turns_text = _format_turns_block(ctx.recent_messages)
        if turns_text:
            sections.append(f"Recent Conversation Turns:\n{turns_text}")

    return "\n\n".join(sections)


def rewrite_question(
    question: str,
    conversation_history: Union[MemoryContext, Sequence[Union[Message, dict]]],
    llm_provider: Optional[BaseLLMProvider] = None,
) -> str:
    """Rewrite a user question into a standalone query using conversation context.

    Supports both three-tier MemoryContext objects and legacy sequences of
    Message or dict objects. Falls back safely to the stripped input question
    on empty context, malformed output, or LLM provider failures.
    """
    stripped_question = (question or "").strip()
    if not stripped_question:
        return stripped_question

    if isinstance(conversation_history, MemoryContext):
        if not conversation_history.has_context:
            return stripped_question
        context_block = _format_memory_context_block(conversation_history)
        if not context_block.strip():
            return stripped_question
        context_header = "Conversation context:"
    else:
        context_block = _format_turns_block(conversation_history)
        context_header = "Conversation history:"

    prompt = f"""
You are a question rewriting component in a cybersecurity RAG system.

Your task is to rewrite the user's latest question into a standalone
question that can be understood without the previous conversation.

{context_header}
{context_block}

Latest user question:
{stripped_question}

Rules:
1. Preserve the original meaning.
2. Use conversation history, session summary, and active standards/context ONLY to resolve pronouns or missing scope in the latest question; if the latest question introduces a new standalone topic, preserve it unchanged.
3. Do not answer the question.
4. Return ONLY the rewritten question.
"""

    active_provider = llm_provider or provider

    try:
        rewritten = active_provider.generate(
            prompt=prompt,
            temperature=0.0,
            max_tokens=settings.query_rewrite_max_tokens,
        )
        cleaned = (rewritten or "").strip()
        return cleaned if cleaned else stripped_question
    except Exception as exc:
        logger.warning("Conversational query rewrite failed (%s); keeping original question.", exc)
        return stripped_question


if __name__ == "__main__":
    history = [
        {
            "user": "What is least privilege?",
            "assistant": "Least privilege limits actions to the minimum necessary.",
        }
    ]

    test_q = "Why is it important?"
    result = rewrite_question(test_q, history)

    print("\nOriginal:", test_q)
    print("Rewritten:", result)
