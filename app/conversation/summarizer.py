"""Incremental rolling conversation summarizer for Cybersecurity RAG memory."""

import logging
from typing import Optional, Sequence

from app.conversation.short_term_memory import TokenCounter
from app.core.interfaces import BaseLLMProvider
from app.core.models import Message

logger = logging.getLogger(__name__)

SUMMARY_PROMPT_TEMPLATE = """You are a conversation state summarizer for a Cybersecurity RAG system.

Merge the CURRENT SUMMARY and NEWLY EVICTED TURNS into one concise, factual summary.

RULES:
1. Preserve exact NIST publication numbers, standards, and frameworks (e.g., NIST SP 800-53, SP 800-144, SP 800-207, SSDF, FedRAMP, RMF).
2. Preserve specific security control IDs, vulnerabilities, and technical identifiers (e.g., AU-3, AC-2, CVE-2024-1234).
3. Preserve the user's system scope, cloud delivery model, and constraints (e.g., multi-tenant SaaS, IaaS, Zero Trust, federal compliance).
4. Preserve any open sub-questions or unresolved investigation threads.
5. Do NOT invent new standards, controls, citations, or technical claims that do not appear in the input.
6. Be concise and output ONLY the updated summary text.

CURRENT SUMMARY:
{existing_summary}

NEWLY EVICTED TURNS:
{turns_block}

UPDATED SUMMARY:"""


class ConversationSummarizer:
    """Compresses aged conversation turns into a bounded rolling session summary."""

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        max_summary_tokens: int = 300,
        token_counter: Optional[TokenCounter] = None,
    ) -> None:
        self.llm_provider: Optional[BaseLLMProvider] = llm_provider
        self.max_summary_tokens: int = max(0, max_summary_tokens)
        self.token_counter: TokenCounter = (
            token_counter if token_counter is not None else TokenCounter()
        )

    def _truncate_to_token_budget(self, text: str) -> str:
        """Trim text along word boundaries to stay within max_summary_tokens."""
        cleaned = " ".join(text.strip().split())
        if not cleaned or self.max_summary_tokens <= 0:
            return "" if self.max_summary_tokens <= 0 else cleaned

        if self.token_counter.count_text(cleaned) <= self.max_summary_tokens:
            return cleaned

        words = cleaned.split(" ")
        lo, hi = 1, len(words)
        best = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = " ".join(words[:mid])
            if self.token_counter.count_text(candidate) <= self.max_summary_tokens:
                best = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        if best:
            return best
        # Single long token exceeds budget: hard char slice bounded by heuristic estimate
        char_cap = max(4, self.max_summary_tokens * 4)
        return cleaned[:char_cap]

    @staticmethod
    def _format_turns(turns: Sequence[Message]) -> str:
        blocks = []
        for idx, turn in enumerate(turns, start=1):
            user_text = " ".join(turn.user.strip().split())
            assistant_text = " ".join(turn.assistant.strip().split())
            blocks.append(f"Turn {idx}:\nUser: {user_text}\nAssistant: {assistant_text}")
        return "\n\n".join(blocks)

    def _deterministic_fallback(
        self,
        existing_summary: str,
        new_turns: Sequence[Message],
    ) -> str:
        """Condense evicted turns deterministically when LLM summarization is unavailable."""
        topics = []
        for turn in new_turns:
            q = " ".join(turn.user.strip().split())
            if q:
                if len(q) > 120:
                    q = q[:117].rstrip() + "..."
                topics.append(q)

        new_part = "Prior topics: " + "; ".join(topics) if topics else ""
        base = " ".join(existing_summary.strip().split())

        if base and new_part:
            combined = f"{base} | {new_part}"
        else:
            combined = base or new_part

        # If existing summary already consumed the budget, prioritize keeping newest topics visible
        if (
            base
            and new_part
            and self.token_counter.count_text(combined) > self.max_summary_tokens
            and self.max_summary_tokens > 0
        ):
            reserve_new = min(
                self.max_summary_tokens // 2 or self.max_summary_tokens,
                self.token_counter.count_text(new_part),
            )
            remaining_for_base = max(0, self.max_summary_tokens - reserve_new - 2)
            if remaining_for_base > 0:
                words = base.split(" ")
                kept_base = ""
                for w in reversed(words):
                    cand = f"{w} {kept_base}".strip()
                    if self.token_counter.count_text(cand) <= remaining_for_base:
                        kept_base = cand
                    else:
                        break
                combined = f"{kept_base} | {new_part}".strip(" |")
            else:
                combined = new_part

        return self._truncate_to_token_budget(combined)

    def summarize(
        self,
        existing_summary: str,
        new_turns: Sequence[Message],
    ) -> str:
        """Merge existing_summary and newly evicted turns into an updated summary."""
        if not new_turns:
            return existing_summary

        if self.max_summary_tokens <= 0:
            return ""

        if self.llm_provider is None:
            return self._deterministic_fallback(existing_summary, new_turns)

        turns_block = self._format_turns(new_turns)
        prior = existing_summary.strip() or "(None)"
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            existing_summary=prior,
            turns_block=turns_block,
        )

        try:
            generated = self.llm_provider.generate(
                prompt,
                temperature=0.0,
                max_tokens=self.max_summary_tokens,
            )
            cleaned = " ".join((generated or "").strip().split())
            if cleaned:
                return self._truncate_to_token_budget(cleaned)
            logger.warning("ConversationSummarizer received empty output; using fallback.")
        except Exception as exc:
            logger.warning("ConversationSummarizer LLM call failed (%s); using fallback.", exc)

        return self._deterministic_fallback(existing_summary, new_turns)
