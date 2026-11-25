"""Unit tests for ShortTermMemory and TokenCounter (Step 2 / Module 1)."""

import sys
import types
import unittest
from unittest.mock import patch

from app.conversation.short_term_memory import ShortTermMemory, TokenCounter
from app.core.models import Message


class TestTokenCounter(unittest.TestCase):
    """Verify tiktoken token counting and offline heuristic fallback."""

    def test_empty_text_returns_zero(self):
        counter = TokenCounter()
        self.assertEqual(counter.count_text(""), 0)

    def test_offline_fallback_when_tiktoken_fails(self):
        fake_tiktoken = types.ModuleType("tiktoken")

        def _raise_offline(_name: str):
            raise OSError("Network unreachable while fetching cl100k_base")

        fake_tiktoken.get_encoding = _raise_offline  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"tiktoken": fake_tiktoken}):
            counter = TokenCounter()
            self.assertEqual(counter.count_text("abcd" * 5), 5)  # 20 // 4 == 5
            self.assertEqual(counter.count_text("hi"), 1)  # max(1, 2 // 4) == 1
            msg = Message(user="abcd" * 4, assistant="efgh" * 4)  # 4 + 4 + 8 = 16
            self.assertEqual(counter.count_message(msg), 16)

    def test_uses_tiktoken_when_encoding_is_available(self):
        class _FakeEncoding:
            def encode(self, text: str):
                return text.split()

        fake_tiktoken = types.ModuleType("tiktoken")
        fake_tiktoken.get_encoding = lambda _name: _FakeEncoding()  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"tiktoken": fake_tiktoken}):
            counter = TokenCounter()
            self.assertEqual(counter.count_text("one two three"), 3)
            msg = Message(user="one two", assistant="three four five")
            self.assertEqual(counter.count_message(msg), 2 + 3 + 8)


class TestShortTermMemory(unittest.TestCase):
    """Verify turn eviction, token-budget trimming, hydration, and clearing."""

    def _make_offline_counter(self) -> TokenCounter:
        counter = TokenCounter()
        counter._tiktoken_failed = True
        return counter

    def test_turn_eviction_when_exceeding_max_recent_messages(self):
        stm = ShortTermMemory(
            max_recent_messages=3,
            max_tokens=5000,
            token_counter=self._make_offline_counter(),
        )
        evicted_all = []
        for idx in range(1, 6):
            evicted = stm.add(Message(user=f"Q{idx}", assistant=f"A{idx}"))
            evicted_all.extend(evicted)

        self.assertEqual([m.user for m in evicted_all], ["Q1", "Q2"])
        self.assertEqual([m.user for m in stm.get_messages()], ["Q3", "Q4", "Q5"])
        self.assertEqual(len(stm), 3)

    def test_token_budget_trims_oldest_turns_chronologically(self):
        counter = self._make_offline_counter()
        stm = ShortTermMemory(
            max_recent_messages=6,
            max_tokens=45,
            token_counter=counter,
        )
        # Each message: 40 chars user (10 tokens) + 40 chars assistant (10 tokens) + 8 = 28 tokens.
        # Budget 45 fits only the newest 1 turn (2 turns = 56 > 45).
        # With budget 60, newest 2 turns (56 <= 60) fit.
        m1 = Message(user="A" * 40, assistant="B" * 40)
        m2 = Message(user="C" * 40, assistant="D" * 40)
        m3 = Message(user="E" * 40, assistant="F" * 40)
        stm.add(m1)
        stm.add(m2)
        stm.add(m3)

        kept_45 = stm.get_messages()
        self.assertEqual([m.user for m in kept_45], ["E" * 40])

        kept_60 = stm.get_messages(max_tokens=60)
        self.assertEqual([m.user for m in kept_60], ["C" * 40, "E" * 40])

    def test_always_preserves_latest_turn_even_if_oversized_when_budget_positive(self):
        counter = self._make_offline_counter()
        stm = ShortTermMemory(
            max_recent_messages=4,
            max_tokens=15,
            token_counter=counter,
        )
        stm.add(Message(user="X" * 20, assistant="Y" * 20))
        stm.add(Message(user="Z" * 200, assistant="W" * 200))

        msgs = stm.get_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].user, "Z" * 200)

        self.assertEqual(stm.get_messages(max_tokens=0), [])

    def test_hydrate_and_clear(self):
        counter = self._make_offline_counter()
        stm = ShortTermMemory(max_recent_messages=2, max_tokens=1000, token_counter=counter)
        stm.hydrate([Message(f"Q{i}", f"A{i}") for i in range(1, 5)])
        self.assertEqual([m.user for m in stm.get_messages()], ["Q3", "Q4"])
        self.assertGreater(stm.total_tokens(), 0)

        stm.clear()
        self.assertEqual(len(stm), 0)
        self.assertEqual(stm.get_messages(), [])


if __name__ == "__main__":
    unittest.main()
