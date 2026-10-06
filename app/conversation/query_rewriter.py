"""Query rewriter for conversational cybersecurity RAG."""

from typing import Any, List, Optional, Union

from app.core.config import settings
from app.core.interfaces import BaseLLMProvider
from app.core.models import Message
from app.generation.providers.groq_provider import GroqProvider

# Model configuration
GROQ_MODEL = settings.llm_model

# Provider instance conforming to BaseLLMProvider
provider: BaseLLMProvider = GroqProvider()


def rewrite_question(
    question: str,
    conversation_history: List[Union[Message, dict]],
    llm_provider: Optional[BaseLLMProvider] = None,
) -> str:
    """Rewrite a user question into a standalone query using conversation context.

    Args:
        question: The latest user question.
        conversation_history: List of past conversation turns.
        llm_provider: Optional provider override conforming to BaseLLMProvider.
            Defaults to the module-level GroqProvider.

    Returns:
        The standalone rewritten question.
    """
    history_text = ""

    for message in conversation_history:
        if isinstance(message, dict):
            user_msg = message.get("user", "")
            assistant_msg = message.get("assistant", "")
        else:
            user_msg = getattr(message, "user", "")
            assistant_msg = getattr(message, "assistant", "")

        history_text += f"""
User: {user_msg}
Assistant: {assistant_msg}
"""

    prompt = f"""
You are a question rewriting component in a cybersecurity RAG system.

Your task is to rewrite the user's latest question into a standalone
question that can be understood without the previous conversation.

Conversation history:
{history_text}

Latest user question:
{question}

Rules:
1. Preserve the original meaning.
2. Use conversation history only when necessary.
3. If the question is already standalone, return it unchanged.
4. Do not answer the question.
5. Return ONLY the rewritten question.
"""

    active_provider = llm_provider or provider

    rewritten = active_provider.generate(
        prompt=prompt,
        temperature=0.0,
        max_tokens=settings.query_rewrite_max_tokens,
    )

    return rewritten.strip()


if __name__ == "__main__":
    history = [
        {
            "user": "What is least privilege?",
            "assistant": "Least privilege limits actions to the minimum necessary."
        }
    ]

    test_q = "Why is it important?"
    result = rewrite_question(test_q, history)

    print("\nOriginal:", test_q)
    print("Rewritten:", result)