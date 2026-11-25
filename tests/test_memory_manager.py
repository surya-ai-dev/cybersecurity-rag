"""Unit tests for unified MemoryManager (Step 4 / Module 5)."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from app.conversation.memory_manager import MemoryManager
from app.conversation.short_term_memory import ShortTermMemory, TokenCounter
from app.conversation.storage import SQLiteMemoryStore
from app.core.interfaces import BaseConversationMemory, BaseMemoryManager
from app.core.models import MemoryContext


class TestMemoryManager(unittest.TestCase):
    """Verify 3-tier MemoryManager orchestration, sessions, persistence, and protocols."""

    def _offline_stm(self, max_recent: int = 4, max_tokens: int = 1500) -> ShortTermMemory:
        tc = TokenCounter()
        tc._tiktoken_failed = True
        return ShortTermMemory(
            max_recent_messages=max_recent,
            max_tokens=max_tokens,
            token_counter=tc,
        )

    def test_protocol_compliance(self):
        self.assertTrue(issubclass(MemoryManager, BaseConversationMemory))
        self.assertTrue(issubclass(MemoryManager, BaseMemoryManager))
        mgr = MemoryManager(short_term=self._offline_stm())
        self.assertIsInstance(mgr, BaseConversationMemory)
        self.assertIsInstance(mgr, BaseMemoryManager)
        mgr.close()

    def test_pure_in_memory_mode_does_not_create_sqlite_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "should_not_exist.sqlite"
            mgr = MemoryManager(
                session_id="mem-only",
                short_term=self._offline_stm(max_recent=3),
                db_path=db_path,
                enable_persistence=False,
                enable_summarization=False,
                enable_long_term=True,
            )
            mgr.add_message("Check NIST SP 800-53 AC-2.", "Account management controls.")
            self.assertFalse(db_path.exists())
            self.assertIsNone(mgr.store)
            self.assertEqual(len(mgr.get_messages()), 1)

            ctx = mgr.get_context("What about AU-3?")
            self.assertEqual({f.key for f in ctx.active_facts}, {"NIST SP 800-53", "AC-2"})
            mgr.close()

    def test_automatic_eviction_and_incremental_summarization_with_persistence(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = lambda prompt, **_kw: "Summary includes NIST SP 800-144 cloud risks (turns 1-4)."

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "mem.sqlite"
            with MemoryManager(
                session_id="sess-sum",
                short_term=self._offline_stm(max_recent=4),
                llm_provider=mock_llm,
                db_path=db_path,
                enable_persistence=True,
                enable_summarization=True,
                enable_long_term=True,
                summarize_after_turns=4,
            ) as mgr:
                for i in range(1, 9):
                    mgr.add_message(
                        f"Question {i} about NIST SP 800-144 SaaS",
                        f"Answer {i}",
                        standalone_question=f"Standalone {i}",
                        source_chunk_ids=[f"NIST_SP_800-144_txt_0000{i}"],
                    )

                self.assertEqual(mock_llm.generate.call_count, 4)  # turns 5, 6, 7, 8 evicted 1, 2, 3, 4
                recent = mgr.get_messages()
                self.assertEqual([m.turn_index for m in recent], [5, 6, 7, 8])

                ctx = mgr.get_context("What about SLAs?")
                self.assertIsInstance(ctx, MemoryContext)
                self.assertTrue(ctx.has_context)
                self.assertIn("NIST SP 800-144", ctx.summary)
                self.assertEqual([m.turn_index for m in ctx.recent_messages], [5, 6, 7, 8])
                self.assertGreater(ctx.total_tokens, 0)
                fact_keys = {f.key for f in ctx.active_facts}
                self.assertTrue({"NIST SP 800-144", "SaaS"}.issubset(fact_keys))

            # Reopen session from SQLite after restart and verify hydration
            with MemoryManager(
                session_id="sess-sum",
                short_term=self._offline_stm(max_recent=4),
                db_path=db_path,
                enable_persistence=True,
                enable_summarization=True,
                enable_long_term=True,
            ) as reopened:
                reopened_ctx = reopened.get_context("SLAs?")
                self.assertIn("NIST SP 800-144", reopened_ctx.summary)
                self.assertEqual([m.turn_index for m in reopened_ctx.recent_messages], [5, 6, 7, 8])
                self.assertEqual(
                    reopened_ctx.recent_messages[0].source_chunk_ids,
                    ["NIST_SP_800-144_txt_00005"],
                )

    def test_session_lifecycle_new_switch_list_and_clear(self):
        with SQLiteMemoryStore(":memory:") as store:
            with MemoryManager(
                session_id="sess-1",
                store=store,
                short_term=self._offline_stm(max_recent=4),
                enable_persistence=True,
                enable_long_term=True,
            ) as mgr:
                mgr.add_message("What is Zero Trust in NIST SP 800-207?", "Removes implicit trust.")
                s2 = mgr.new_session(title="Incident Response")
                self.assertNotEqual(s2.session_id, "sess-1")
                self.assertEqual(mgr.get_messages(), [])

                mgr.add_message("Explain AU-3 audit logs.", "Six mandatory audit fields.")
                sessions = mgr.list_sessions()
                self.assertEqual(len(sessions), 2)

                # Switch back to sess-1 and verify state hydration
                switched = mgr.switch_session("sess-1")
                self.assertEqual(switched.session_id, "sess-1")
                self.assertEqual(
                    [m.user for m in mgr.get_messages()],
                    ["What is Zero Trust in NIST SP 800-207?"],
                )

                # Cross-session get_context query
                other_ctx = mgr.get_context("audit", session_id=s2.session_id)
                self.assertEqual(other_ctx.session_id, s2.session_id)
                self.assertEqual([m.user for m in other_ctx.recent_messages], ["Explain AU-3 audit logs."])

                # Clear active session wipes working memory and persisted rows
                mgr.clear()
                self.assertEqual(mgr.get_messages(), [])
                self.assertFalse(mgr.get_context().has_context)
                self.assertEqual(len(mgr.list_sessions()), 1)


if __name__ == "__main__":
    unittest.main()
