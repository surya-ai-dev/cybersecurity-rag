"""Integration tests for Step 5 (Module 6): Rewriter, RAGEngine, and CLI Memory Integration."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.conversation.memory_manager import MemoryManager
from app.conversation.query_rewriter import rewrite_question
from app.conversation.short_term_memory import ShortTermMemory, TokenCounter
from app.core.interfaces import BaseConversationMemory
from app.core.models import ChunkMetadata, MemoryContext, MemoryFact, Message, RetrievedChunk
from app.pipeline.engine import RAGEngine
from main import handle_cli_command


class TestMemoryContextQueryRewriter(unittest.TestCase):
    """Verify rewrite_question supports three-tier MemoryContext and safe fallbacks."""

    def test_rewrites_with_three_tier_memory_context_and_omits_empty_sections(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (
            "What SLA compliance obligations apply to public cloud providers under NIST SP 800-144?"
        )
        ctx = MemoryContext(
            session_id="s1",
            summary="Investigating public cloud risks in NIST SP 800-144.",
            active_facts=[
                MemoryFact("f1", "s1", "standard", "NIST SP 800-144", "Public Cloud Security"),
                MemoryFact("f2", "s1", "environment", "SaaS", "SaaS cloud deployment"),
            ],
            recent_messages=[
                Message("What monitoring problems exist?", "Limited provider log visibility [Source 1].")
            ],
        )

        rewritten = rewrite_question("What did it say about SLAs?", ctx, llm_provider=mock_llm)
        self.assertIn("NIST SP 800-144", rewritten)
        prompt = mock_llm.generate.call_args.kwargs["prompt"]
        self.assertIn("Session Summary:", prompt)
        self.assertIn("Active Technical Context / Standards:", prompt)
        self.assertIn("Recent Conversation Turns:", prompt)
        self.assertIn("NIST SP 800-144", prompt)
        self.assertIn("SaaS", prompt)

        # Partial context with summary only omits Facts & Recent Turns headers
        mock_llm.reset_mock()
        summary_only = MemoryContext(summary="Prior discussion of Zero Trust.")
        rewrite_question("Clarify PEPs there.", summary_only, llm_provider=mock_llm)
        prompt_summary_only = mock_llm.generate.call_args.kwargs["prompt"]
        self.assertIn("Session Summary:", prompt_summary_only)
        self.assertNotIn("Active Technical Context / Standards:", prompt_summary_only)
        self.assertNotIn("Recent Conversation Turns:", prompt_summary_only)

    def test_empty_memory_context_skips_llm_call(self):
        mock_llm = MagicMock()
        empty_ctx = MemoryContext()
        out = rewrite_question("  What is AU-3?  ", empty_ctx, llm_provider=mock_llm)
        self.assertEqual(out, "What is AU-3?")
        mock_llm.generate.assert_not_called()

    def test_rewriter_falls_back_safely_on_error_or_empty_output(self):
        ctx = MemoryContext(summary="Prior context.")

        err_llm = MagicMock()
        err_llm.generate.side_effect = RuntimeError("Groq down")
        self.assertEqual(
            rewrite_question("  Explain CP-9 backups  ", ctx, llm_provider=err_llm),
            "Explain CP-9 backups",
        )

        empty_llm = MagicMock()
        empty_llm.generate.return_value = "   "
        self.assertEqual(
            rewrite_question("Explain CP-9 backups", ctx, llm_provider=empty_llm),
            "Explain CP-9 backups",
        )

    def test_legacy_list_history_compatibility(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Why is least privilege important?"
        out = rewrite_question(
            "Why is it important?",
            [{"user": "What is least privilege?", "assistant": "Minimal access rights."}],
            llm_provider=mock_llm,
        )
        self.assertEqual(out, "Why is least privilege important?")
        mock_llm.generate.assert_called_once()


class TestRAGEngineMemoryIntegration(unittest.TestCase):
    """Verify RAGEngine.query()/stream() with MemoryManager, mocks, and grounding."""

    def _make_retriever_and_reranker(self):
        retriever = MagicMock()
        retriever.retrieve.return_value = [
            RetrievedChunk(
                chunk_id="NIST_SP_800-144_txt_00113",
                text="Service agreements must define compliance audits and data return on termination.",
                dense_score=0.84,
                metadata=ChunkMetadata(document_id="NIST_SP_800-144", section="5.3"),
            )
        ]
        reranker = MagicMock()
        reranker.rerank.side_effect = lambda _q, docs, top_n: list(docs)[:top_n]
        return retriever, reranker

    def test_query_and_stream_persist_provenance_to_sqlite_and_preserve_grounding(self):
        retriever, reranker = self._make_retriever_and_reranker()
        llm = MagicMock()

        def generate_side_effect(prompt, **_kwargs):
            # Rewrite prompt vs final answer prompt
            if "question rewriting component" in prompt:
                return "What contractual terms must cloud SLAs define under NIST SP 800-144?"
            # Verify grounding prompt uses retrieved chunk content and does NOT cite memory as [Source X]
            self.assertIn("RETRIEVED CONTEXT:", prompt)
            self.assertIn("Service agreements must define compliance audits", prompt)
            self.assertIn("include [Source X]", prompt)
            return "SLAs must define compliance audits and data return [Source 1]."

        llm.generate.side_effect = generate_side_effect
        llm.stream.return_value = iter(["SLAs define ", "compliance audits [Source 1]."])

        tc = TokenCounter()
        tc._tiktoken_failed = True

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "rag_memory.sqlite"
            mgr = MemoryManager(
                session_id="sess-e2e",
                short_term=ShortTermMemory(max_recent_messages=6, max_tokens=1500, token_counter=tc),
                llm_provider=llm,
                db_path=db_path,
                enable_persistence=True,
                enable_summarization=False,
                enable_long_term=True,
            )

            engine = RAGEngine(
                retriever=retriever,
                reranker=reranker,
                llm_provider=llm,
                memory=mgr,
                enable_reranking=True,
            )

            try:
                # Turn 1: standalone query (no prior context -> no rewrite call)
                r1 = engine.query("Explain NIST SP 800-144 cloud governance.", stream=False)
                self.assertEqual(r1.standalone_question, "Explain NIST SP 800-144 cloud governance.")
                self.assertIn("[Source 1]", r1.answer)

                # Turn 2: follow-up pronoun query via stream() -> passes MemoryContext to rewriter
                streamed = "".join(engine.stream("What about SLAs there?"))
                self.assertEqual(streamed, "SLAs define compliance audits [Source 1].")

                persisted = mgr.store.get_recent_turns("sess-e2e", limit=5)  # type: ignore[union-attr]
                self.assertEqual(len(persisted), 2)
                self.assertEqual(persisted[0].source_chunk_ids, ["NIST_SP_800-144_txt_00113"])
                self.assertEqual(
                    persisted[1].standalone_question,
                    "What contractual terms must cloud SLAs define under NIST SP 800-144?",
                )
                self.assertEqual(persisted[1].source_chunk_ids, ["NIST_SP_800-144_txt_00113"])
            finally:
                engine.close()

    def test_backward_compatibility_with_simple_memory_and_unspecd_mock(self):
        retriever, reranker = self._make_retriever_and_reranker()
        llm = MagicMock()
        llm.generate.return_value = "Grounded answer [Source 1]."

        # Un-spec'd MagicMock must still receive exact 2-arg add_message(question, answer)
        unspecd_mock = MagicMock()
        unspecd_mock.get_messages.return_value = []
        engine_mock = RAGEngine(
            retriever=retriever,
            reranker=reranker,
            llm_provider=llm,
            memory=unspecd_mock,
            enable_reranking=False,
        )
        engine_mock.query("What is AU-3?", stream=False)
        unspecd_mock.add_message.assert_called_once_with("What is AU-3?", "Grounded answer [Source 1].")

        # Spec'd BaseConversationMemory receives exact 2-arg call as well
        spec_mock = MagicMock(spec=BaseConversationMemory)
        spec_mock.get_messages.return_value = []
        engine_spec = RAGEngine(
            retriever=retriever,
            reranker=reranker,
            llm_provider=llm,
            memory=spec_mock,
            enable_reranking=False,
        )
        engine_spec.query("What is CP-9?", stream=False)
        spec_mock.add_message.assert_called_once_with("What is CP-9?", "Grounded answer [Source 1].")

    def test_engine_initializes_memory_manager_when_persistent_flag_enabled(self):
        retriever, reranker = self._make_retriever_and_reranker()
        llm = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "auto_mgr.sqlite"
            with patch("app.pipeline.engine.settings") as mock_settings:
                mock_settings.enable_persistent_memory = True
                mock_settings.enable_memory_summarization = False
                mock_settings.enable_long_term_memory = False
                mock_settings.enable_query_rewriting = False
                mock_settings.enable_adaptive_query_rewriting = False
                mock_settings.dense_top_k = 20
                mock_settings.final_top_n = 5
                mock_settings.enable_reranking = False

                with patch("app.conversation.memory_manager.settings") as mgr_settings:
                    mgr_settings.enable_persistent_memory = True
                    mgr_settings.enable_memory_summarization = False
                    mgr_settings.enable_long_term_memory = False
                    mgr_settings.memory_summarize_after_turns = 6
                    mgr_settings.memory_long_term_top_k = 3
                    mgr_settings.conversation_history_limit = 6
                    mgr_settings.memory_max_history_tokens = 1500
                    mgr_settings.memory_max_summary_tokens = 300
                    mgr_settings.memory_db_path = db_path

                    engine = RAGEngine(
                        retriever=retriever,
                        reranker=reranker,
                        llm_provider=llm,
                        session_id="sess-auto",
                    )
                    try:
                        self.assertIsInstance(engine.memory, MemoryManager)
                        self.assertEqual(engine.memory.session_id, "sess-auto")
                        self.assertTrue(db_path.exists())
                    finally:
                        engine.close()


class TestCLISessionCommands(unittest.TestCase):
    """Verify CLI slash commands (/new, /sessions, /load, /memory, /clear) in main.py."""

    def test_cli_memory_commands_workflow(self):
        retriever = MagicMock()
        reranker = MagicMock()
        llm = MagicMock()
        tc = TokenCounter()
        tc._tiktoken_failed = True

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MemoryManager(
                session_id="cli-1",
                short_term=ShortTermMemory(max_recent_messages=6, max_tokens=1500, token_counter=tc),
                db_path=Path(tmpdir) / "cli.sqlite",
                enable_persistence=True,
                enable_long_term=True,
            )
            mgr.add_message("NIST SP 800-53 SI-2 question", "Patch management answer.")
            engine = RAGEngine(
                retriever=retriever,
                reranker=reranker,
                llm_provider=llm,
                memory=mgr,
            )

            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertTrue(handle_cli_command("/memory", engine))
                    self.assertTrue(handle_cli_command("/sessions", engine))
                    self.assertTrue(handle_cli_command("/new Second Audit", engine))
                    self.assertTrue(handle_cli_command("/load cli-1", engine))
                    self.assertTrue(handle_cli_command("/clear", engine))
                    self.assertFalse(handle_cli_command("What is Zero Trust?", engine))

                out = buf.getvalue()
                self.assertIn("Session ID : cli-1", out)
                self.assertIn("SI-2", out)
                self.assertIn("Started new session:", out)
                self.assertIn("Loaded session: cli-1", out)
                self.assertIn("Cleared active session memory.", out)
            finally:
                engine.close()


if __name__ == "__main__":
    unittest.main()
