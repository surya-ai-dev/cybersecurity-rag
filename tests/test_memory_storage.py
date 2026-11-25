"""Unit tests for SQLiteMemoryStore (Step 2 / Module 2)."""

from array import array
from pathlib import Path
import tempfile
import unittest

from app.conversation.storage import SQLiteMemoryStore
from app.core.models import MemoryFact, Message


class TestSQLiteMemoryStore(unittest.TestCase):
    """Verify SQLite persistence, multi-session isolation, facts, embeddings, and cascades."""

    def test_schema_and_parent_directory_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nested" / "memory" / "memory.sqlite"
            with SQLiteMemoryStore(db_path) as store:
                self.assertTrue(db_path.exists())
                conn = store._require_conn()
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                self.assertTrue(
                    {"sessions", "turns", "memory_facts", "episodic_embeddings"}.issubset(tables)
                )
                indexes = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    ).fetchall()
                }
                self.assertIn("idx_turns_session_idx", indexes)
                self.assertIn("idx_facts_unique", indexes)

    def test_session_isolation_and_listing(self):
        with SQLiteMemoryStore(":memory:") as store:
            s1 = store.create_session(session_id="sess-a", title="Cloud Security")
            s2 = store.create_session(session_id="sess-b", title="Zero Trust")
            self.assertEqual(s1.session_id, "sess-a")
            self.assertEqual(s2.session_id, "sess-b")

            store.append_turn("sess-a", Message("Cloud question?", "Cloud answer."))
            store.append_turn("sess-b", Message("ZTA question?", "ZTA answer."))

            a_turns = store.get_recent_turns("sess-a", limit=10)
            b_turns = store.get_recent_turns("sess-b", limit=10)
            self.assertEqual([t.user for t in a_turns], ["Cloud question?"])
            self.assertEqual([t.user for t in b_turns], ["ZTA question?"])

            listed = store.list_sessions()
            self.assertEqual({s.session_id for s in listed}, {"sess-a", "sess-b"})
            self.assertEqual(store.get_session("sess-a").turn_count, 1)

    def test_restart_persistence_roundtrip_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.sqlite"
            with SQLiteMemoryStore(db_path) as store:
                idx1 = store.append_turn(
                    "sess-persist",
                    Message(
                        user="What are cloud monitoring challenges?",
                        assistant="Logs may lack visibility [Source 1].",
                        standalone_question="What monitoring challenges exist in public clouds?",
                        source_chunk_ids=["NIST_SP_800-144_txt_00065", "NIST_SP_800-146_txt_00134"],
                        timestamp="2026-11-25T11:40:00Z",
                    ),
                )
                idx2 = store.append_turn(
                    "sess-persist",
                    Message(user="What about SLAs?", assistant="SLAs define audits [Source 1]."),
                )
                self.assertEqual(idx1, 1)
                self.assertEqual(idx2, 2)
                store.update_summary("sess-persist", "Reviewed cloud monitoring.", last_summarized_turn_index=1)

            # Reopen fresh store pointing to the exact same SQLite file
            with SQLiteMemoryStore(db_path) as reopened:
                session = reopened.get_session("sess-persist")
                self.assertIsNotNone(session)
                self.assertEqual(session.turn_count, 2)
                self.assertEqual(session.summary, "Reviewed cloud monitoring.")
                self.assertEqual(session.title, "What are cloud monitoring challenges?")

                turns = reopened.get_recent_turns("sess-persist", limit=6)
                self.assertEqual(len(turns), 2)
                self.assertEqual(turns[0].turn_index, 1)
                self.assertEqual(turns[0].standalone_question, "What monitoring challenges exist in public clouds?")
                self.assertEqual(turns[0].source_chunk_ids, ["NIST_SP_800-144_txt_00065", "NIST_SP_800-146_txt_00134"])
                self.assertEqual(turns[1].turn_index, 2)

                unsummarized = reopened.get_unsummarized_turns("sess-persist")
                self.assertEqual([t.turn_index for t in unsummarized], [2])

    def test_fact_upsert_deduplication_and_embedding_roundtrip(self):
        with SQLiteMemoryStore(":memory:") as store:
            store.create_session("sess-facts")
            vec1 = [0.6, 0.8, 0.0]
            store.upsert_fact(
                MemoryFact(
                    fact_id="f-1",
                    session_id="sess-facts",
                    category="standard",
                    key="NIST_SP_800-53",
                    value="Initial description",
                    source_turn=1,
                    confidence=0.8,
                ),
                embedding=vec1,
            )

            # Duplicate (session_id, category, key) should update in place, not insert duplicate row
            vec2 = [1.0, 0.0, 0.0]
            store.upsert_fact(
                MemoryFact(
                    fact_id="f-2-ignored-on-conflict",
                    session_id="sess-facts",
                    category="standard",
                    key="NIST_SP_800-53",
                    value="Updated description",
                    source_turn=3,
                    confidence=1.0,
                ),
                embedding=vec2,
            )

            facts = store.get_facts(session_id="sess-facts")
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0].value, "Updated description")
            self.assertEqual(facts[0].source_turn, 3)

            emb_rows = store.get_fact_embeddings(session_id="sess-facts")
            self.assertEqual(len(emb_rows), 1)
            fact_obj, blob, dim = emb_rows[0]
            self.assertEqual(dim, 3)
            decoded = array("f")
            decoded.frombytes(blob)
            self.assertAlmostEqual(decoded[0], 1.0, places=5)
            self.assertEqual(fact_obj.key, "NIST_SP_800-53")

    def test_delete_session_cascades_all_child_rows(self):
        with SQLiteMemoryStore(":memory:") as store:
            store.create_session("sess-del")
            store.append_turn("sess-del", Message("Q", "A"))
            store.upsert_fact(
                MemoryFact("f1", "sess-del", "control", "AU-3", "Audit record content"),
                embedding=[0.5, 0.5],
            )
            store.delete_session("sess-del")

            self.assertIsNone(store.get_session("sess-del"))
            self.assertEqual(store.get_recent_turns("sess-del"), [])
            self.assertEqual(store.get_facts("sess-del"), [])
            self.assertEqual(store.get_fact_embeddings("sess-del"), [])

    def test_parameterized_queries_handle_sql_injection_strings_safely(self):
        with SQLiteMemoryStore(":memory:") as store:
            malicious_sid = "sess'; DROP TABLE turns; --"
            malicious_q = "What is '1'='1' OR 1=1; DELETE FROM sessions; --"
            store.append_turn(malicious_sid, Message(malicious_q, "Safe response; --"))
            store.upsert_fact(
                MemoryFact("f-inj", malicious_sid, "standard", "SP';--", malicious_q)
            )

            turns = store.get_recent_turns(malicious_sid)
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0].user, malicious_q)
            self.assertEqual(len(store.get_facts(malicious_sid)), 1)


if __name__ == "__main__":
    unittest.main()
