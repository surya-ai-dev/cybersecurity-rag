"""Unit tests for ConversationSummarizer (Step 3 / Module 3)."""

import unittest
from unittest.mock import MagicMock

from app.conversation.short_term_memory import TokenCounter
from app.conversation.summarizer import ConversationSummarizer
from app.core.models import Message


class TestConversationSummarizer(unittest.TestCase):
    """Verify rolling summarization, prompt construction, fallbacks, and token bounds."""

    def _offline_counter(self) -> TokenCounter:
        counter = TokenCounter()
        counter._tiktoken_failed = True
        return counter

    def test_empty_turns_returns_existing_summary_without_calling_llm(self):
        mock_llm = MagicMock()
        summarizer = ConversationSummarizer(
            llm_provider=mock_llm,
            max_summary_tokens=300,
            token_counter=self._offline_counter(),
        )
        result = summarizer.summarize("Prior NIST SP 800-53 summary.", [])
        self.assertEqual(result, "Prior NIST SP 800-53 summary.")
        mock_llm.generate.assert_not_called()

    def test_incremental_summarization_prompt_includes_summary_and_turns(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (
            "Discussed NIST SP 800-144 cloud governance and AU-3 audit record requirements for SaaS."
        )
        summarizer = ConversationSummarizer(
            llm_provider=mock_llm,
            max_summary_tokens=300,
            token_counter=self._offline_counter(),
        )
        turns = [
            Message("What does AU-3 require in NIST SP 800-53?", "Six elements for audit logs [Source 1]."),
            Message("How does it apply to SaaS?", "Provider and consumer logging duties [Source 2]."),
        ]

        out = summarizer.summarize("Initial focus: NIST SP 800-144.", turns)
        self.assertIn("NIST SP 800-144", out)
        self.assertIn("AU-3", out)
        mock_llm.generate.assert_called_once()
        prompt_arg = mock_llm.generate.call_args.args[0]
        self.assertIn("Initial focus: NIST SP 800-144.", prompt_arg)
        self.assertIn("What does AU-3 require in NIST SP 800-53?", prompt_arg)
        self.assertIn("How does it apply to SaaS?", prompt_arg)

    def test_fallback_when_llm_raises_or_returns_empty_or_is_none(self):
        turns = [
            Message("What are NIST SP 800-53 AC-2 rules?", "Account management controls."),
            Message("What about SI-2 flaw remediation?", "Patch testing and deployment."),
        ]

        # 1. LLM raises TimeoutError
        failing_llm = MagicMock()
        failing_llm.generate.side_effect = TimeoutError("Groq timeout")
        summarizer_err = ConversationSummarizer(
            llm_provider=failing_llm,
            max_summary_tokens=150,
            token_counter=self._offline_counter(),
        )
        res_err = summarizer_err.summarize("Baseline scope: SaaS", turns)
        self.assertIn("Baseline scope: SaaS", res_err)
        self.assertIn("AC-2", res_err)
        self.assertIn("SI-2", res_err)

        # 2. LLM returns empty whitespace
        empty_llm = MagicMock()
        empty_llm.generate.return_value = "   \n "
        summarizer_empty = ConversationSummarizer(
            llm_provider=empty_llm,
            max_summary_tokens=150,
            token_counter=self._offline_counter(),
        )
        res_empty = summarizer_empty.summarize("", turns)
        self.assertIn("NIST SP 800-53 AC-2", res_empty)

        # 3. llm_provider is None
        summarizer_none = ConversationSummarizer(
            llm_provider=None,
            max_summary_tokens=150,
            token_counter=self._offline_counter(),
        )
        res_none = summarizer_none.summarize("", turns)
        self.assertIn("SI-2", res_none)

    def test_output_truncated_within_max_summary_tokens(self):
        counter = self._offline_counter()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "word " * 400
        summarizer = ConversationSummarizer(
            llm_provider=mock_llm,
            max_summary_tokens=20,
            token_counter=counter,
        )
        res = summarizer.summarize("", [Message("Q1", "A1")])
        self.assertGreater(len(res), 0)
        self.assertLessEqual(counter.count_text(res), 20)

        zero_budget = ConversationSummarizer(
            llm_provider=mock_llm,
            max_summary_tokens=0,
            token_counter=counter,
        )
        self.assertEqual(zero_budget.summarize("old", [Message("Q1", "A1")]), "")


if __name__ == "__main__":
    unittest.main()
