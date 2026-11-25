"""Unit tests for Step 1 (Module 0): Core Memory Models, Protocols, and Configuration."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings
from app.core.interfaces import BaseConversationMemory, BaseMemoryManager
from app.core.models import (
    MemoryContext,
    MemoryFact,
    Message,
    SessionMetadata,
)


class TestExtendedMessageModel(unittest.TestCase):
    """Verify backward compatibility and extended fields on Message."""

    def test_backward_compatible_positional_and_dict_access(self):
        msg = Message("What is zero trust?", "Zero trust removes implicit trust.")
        self.assertEqual(msg.user, "What is zero trust?")
        self.assertEqual(msg.assistant, "Zero trust removes implicit trust.")
        self.assertIsNone(msg.timestamp)
        self.assertIsNone(msg.standalone_question)
        self.assertEqual(msg.source_chunk_ids, [])
        self.assertIsNone(msg.turn_index)

        self.assertEqual(msg["user"], "What is zero trust?")
        self.assertEqual(msg.get("assistant"), "Zero trust removes implicit trust.")
        self.assertEqual(msg.get("timestamp", "missing"), "missing")

        as_dict = msg.to_dict()
        self.assertEqual(
            as_dict,
            {
                "user": "What is zero trust?",
                "assistant": "Zero trust removes implicit trust.",
            },
        )

    def test_extended_fields_round_trip_serialization(self):
        msg = Message(
            user="What about SLAs there?",
            assistant="SLAs should define compliance terms [Source 1].",
            timestamp="2026-11-25T11:20:00Z",
            standalone_question="What should cloud SLAs define under NIST SP 800-144?",
            source_chunk_ids=["NIST_SP_800-144_txt_00113"],
            turn_index=0,
        )
        serialized = msg.to_dict()
        self.assertEqual(serialized["timestamp"], "2026-11-25T11:20:00Z")
        self.assertEqual(
            serialized["standalone_question"],
            "What should cloud SLAs define under NIST SP 800-144?",
        )
        self.assertEqual(serialized["source_chunk_ids"], ["NIST_SP_800-144_txt_00113"])
        self.assertEqual(serialized["turn_index"], 0)
        self.assertEqual(msg["turn_index"], 0)
        self.assertEqual(msg.get("turn_index"), 0)

        restored = Message.from_dict(serialized)
        self.assertEqual(restored, msg)

    def test_from_dict_defaults_missing_or_null_optional_keys(self):
        restored = Message.from_dict(
            {
                "user": "Hello",
                "assistant": "Hi",
                "source_chunk_ids": None,
                "turn_index": None,
            }
        )
        self.assertEqual(restored.user, "Hello")
        self.assertEqual(restored.assistant, "Hi")
        self.assertIsNone(restored.timestamp)
        self.assertIsNone(restored.standalone_question)
        self.assertEqual(restored.source_chunk_ids, [])
        self.assertIsNone(restored.turn_index)

    def test_getitem_raises_key_error_on_unknown_field(self):
        msg = Message("Q", "A")
        with self.assertRaises(KeyError):
            _ = msg["nonexistent"]
        self.assertEqual(msg.get("nonexistent", "fallback"), "fallback")


class TestMemoryDomainModels(unittest.TestCase):
    """Verify SessionMetadata, MemoryFact, and MemoryContext behavior."""

    def test_session_metadata_defaults_and_values(self):
        session = SessionMetadata(session_id="sess-001")
        self.assertEqual(session.session_id, "sess-001")
        self.assertEqual(session.title, "New Session")
        self.assertEqual(session.summary, "")
        self.assertEqual(session.turn_count, 0)
        self.assertEqual(session.created_at, "")
        self.assertEqual(session.updated_at, "")

    def test_memory_fact_defaults_and_values(self):
        fact = MemoryFact(
            fact_id="fact-1",
            session_id="sess-001",
            category="standard",
            key="NIST_SP_800-53",
            value="Active referenced standard: NIST SP 800-53",
            source_turn=2,
            confidence=0.95,
            updated_at="2026-11-25T11:20:00Z",
        )
        self.assertEqual(fact.category, "standard")
        self.assertEqual(fact.source_turn, 2)
        self.assertEqual(fact.confidence, 0.95)

        default_fact = MemoryFact(
            fact_id="f2",
            session_id="s1",
            category="control",
            key="AC-2",
            value="Account Management",
        )
        self.assertIsNone(default_fact.source_turn)
        self.assertEqual(default_fact.confidence, 1.0)
        self.assertEqual(default_fact.updated_at, "")

    def test_memory_context_has_context(self):
        empty = MemoryContext()
        self.assertFalse(empty.has_context)

        whitespace_only = MemoryContext(summary="   \n\t  ")
        self.assertFalse(whitespace_only.has_context)

        with_summary = MemoryContext(summary="Discussed NIST SP 800-144 cloud risks.")
        self.assertTrue(with_summary.has_context)

        with_messages = MemoryContext(recent_messages=[Message("Q", "A")])
        self.assertTrue(with_messages.has_context)

        with_facts = MemoryContext(
            active_facts=[
                MemoryFact("f1", "s1", "standard", "SP 800-53", "NIST SP 800-53")
            ]
        )
        self.assertTrue(with_facts.has_context)


class _CompliantMemoryManager:
    """Minimal compliant implementation for BaseMemoryManager protocol testing."""

    def add_message(self, user_message: str, assistant_message: str) -> None:
        pass

    def get_messages(self):
        return []

    def get_context(self, query: str = "", session_id=None) -> MemoryContext:
        return MemoryContext(session_id=session_id)

    def clear(self, session_id=None) -> None:
        pass

    def close(self) -> None:
        pass


class _IncompleteMemory:
    """Implements BaseConversationMemory only, missing BaseMemoryManager methods."""

    def add_message(self, user_message: str, assistant_message: str) -> None:
        pass

    def get_messages(self):
        return []


class TestMemoryProtocols(unittest.TestCase):
    """Verify BaseConversationMemory and BaseMemoryManager runtime protocol checks."""

    def test_runtime_protocol_compliance(self):
        compliant = _CompliantMemoryManager()
        incomplete = _IncompleteMemory()

        self.assertIsInstance(compliant, BaseConversationMemory)
        self.assertIsInstance(compliant, BaseMemoryManager)
        self.assertTrue(issubclass(_CompliantMemoryManager, BaseMemoryManager))

        self.assertIsInstance(incomplete, BaseConversationMemory)
        self.assertNotIsInstance(incomplete, BaseMemoryManager)


class TestMemorySettingsConfig(unittest.TestCase):
    """Verify Settings defaults and environment variable overrides for memory."""

    def test_default_memory_settings(self):
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("MEMORY_")
            and k
            not in {
                "ENABLE_PERSISTENT_MEMORY",
                "ENABLE_MEMORY_SUMMARIZATION",
                "ENABLE_LONG_TERM_MEMORY",
            }
        }
        with patch.dict(os.environ, clean_env, clear=True):
            cfg = Settings()
            self.assertEqual(cfg.memory_dir, cfg.data_dir / "memory")
            self.assertEqual(cfg.memory_db_path, cfg.memory_dir / "memory.sqlite")
            self.assertFalse(cfg.enable_persistent_memory)
            self.assertFalse(cfg.enable_memory_summarization)
            self.assertFalse(cfg.enable_long_term_memory)
            self.assertEqual(cfg.memory_max_history_tokens, 1500)
            self.assertEqual(cfg.memory_max_summary_tokens, 300)
            self.assertEqual(cfg.memory_summarize_after_turns, 6)
            self.assertEqual(cfg.memory_long_term_top_k, 3)

    def test_memory_settings_env_overrides(self):
        overrides = {
            "MEMORY_DB_PATH": "/tmp/custom_memory.sqlite",
            "ENABLE_PERSISTENT_MEMORY": "true",
            "ENABLE_MEMORY_SUMMARIZATION": "1",
            "ENABLE_LONG_TERM_MEMORY": "yes",
            "MEMORY_MAX_HISTORY_TOKENS": "2048",
            "MEMORY_MAX_SUMMARY_TOKENS": "450",
            "MEMORY_SUMMARIZE_AFTER_TURNS": "10",
            "MEMORY_LONG_TERM_TOP_K": "5",
        }
        with patch.dict(os.environ, overrides, clear=False):
            cfg = Settings()
            self.assertEqual(cfg.memory_db_path, Path("/tmp/custom_memory.sqlite"))
            self.assertTrue(cfg.enable_persistent_memory)
            self.assertTrue(cfg.enable_memory_summarization)
            self.assertTrue(cfg.enable_long_term_memory)
            self.assertEqual(cfg.memory_max_history_tokens, 2048)
            self.assertEqual(cfg.memory_max_summary_tokens, 450)
            self.assertEqual(cfg.memory_summarize_after_turns, 10)
            self.assertEqual(cfg.memory_long_term_top_k, 5)


if __name__ == "__main__":
    unittest.main()
