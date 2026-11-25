"""Integration tests for FastAPI backend endpoints and SQLite session persistence."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.conversation.memory_manager import MemoryManager
from app.conversation.short_term_memory import ShortTermMemory, TokenCounter
from app.core.models import ChunkMetadata, RetrievedChunk
from app.pipeline.engine import RAGEngine


def _parse_sse_events(raw_body: str):
    """Parse SSE text/event-stream response body into (event, data_dict) pairs."""
    events = []
    for block in raw_body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_raw = "{}"
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_raw = line[len("data:") :].strip()
        events.append((event_name, json.loads(data_raw)))
    return events


class TestAPIEndpoints(unittest.TestCase):
    """Verify /api/v1 endpoints with TestClient, temp SQLite DB, and mocked RAG components."""

    def _build_mock_engine(self, db_path: Path, session_id: str = "init-session") -> RAGEngine:
        retriever = MagicMock()
        retriever.retrieve.return_value = [
            RetrievedChunk(
                chunk_id="NIST_SP_800-144_txt_00113",
                text="Service agreements must establish explicit compliance audits and data return on termination.",
                dense_score=0.86,
                rrf_score=0.032787,
                metadata=ChunkMetadata(
                    document_id="NIST_SP_800-144",
                    source_file="NIST_SP_800-144.pdf",
                    section="5.3 Initiating and Coincident Activities",
                    extra={"page_start": 51},
                ),
            )
        ]

        reranker = MagicMock()
        reranker.rerank.side_effect = lambda _q, docs, top_n: list(docs)[:top_n]

        llm = MagicMock()

        def _generate(prompt: str, **_kwargs) -> str:
            if "question rewriting component" in prompt:
                return "What SLA compliance terms are required under NIST SP 800-144?"
            return "Cloud service agreements must specify compliance audits and termination obligations [Source 1]."

        llm.generate.side_effect = _generate
        llm.stream.return_value = iter(["SLAs must ", "define audits ", "[Source 1]."])

        tc = TokenCounter()
        tc._tiktoken_failed = True
        mgr = MemoryManager(
            session_id=session_id,
            short_term=ShortTermMemory(max_recent_messages=6, max_tokens=1500, token_counter=tc),
            llm_provider=llm,
            db_path=db_path,
            enable_persistence=True,
            enable_summarization=False,
            enable_long_term=True,
        )

        return RAGEngine(
            retriever=retriever,
            reranker=reranker,
            llm_provider=llm,
            memory=mgr,
            enable_reranking=True,
        )

    def test_health_endpoint_reports_flags_and_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "api_health.sqlite"
            engine = self._build_mock_engine(db_path, session_id="health-sess")
            app = create_app(engine=engine)

            with TestClient(app) as client:
                resp = client.get("/api/v1/health")
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data["status"], "ok")
                self.assertTrue(data["persistent_memory_enabled"])
                self.assertFalse(data["summarization_enabled"])
                self.assertTrue(data["long_term_memory_enabled"])
                self.assertEqual(data["active_session_id"], "health-sess")

    def test_chat_creates_session_and_persists_across_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "api_chat.sqlite"
            engine = self._build_mock_engine(db_path)
            app = create_app(engine=engine)

            with TestClient(app) as client:
                # 1. Chat without session_id creates a new session automatically
                resp1 = client.post(
                    "/api/v1/chat",
                    json={"question": "Explain NIST SP 800-144 cloud governance."},
                )
                self.assertEqual(resp1.status_code, 200)
                body1 = resp1.json()
                sid = body1["session_id"]
                self.assertTrue(sid)
                self.assertEqual(body1["standalone_question"], "Explain NIST SP 800-144 cloud governance.")
                self.assertIn("[Source 1]", body1["answer"])
                self.assertEqual(len(body1["sources"]), 1)
                self.assertEqual(body1["sources"][0]["chunk_id"], "NIST_SP_800-144_txt_00113")
                self.assertEqual(body1["sources"][0]["page"], 51)
                self.assertEqual(body1["memory_context"]["recent_turn_count"], 1)

                # 2. Follow-up on same session triggers memory-aware query rewrite
                resp2 = client.post(
                    "/api/v1/chat",
                    json={"question": "What about SLAs there?", "session_id": sid},
                )
                self.assertEqual(resp2.status_code, 200)
                body2 = resp2.json()
                self.assertEqual(body2["session_id"], sid)
                self.assertEqual(
                    body2["standalone_question"],
                    "What SLA compliance terms are required under NIST SP 800-144?",
                )

            # Simulate server restart / reload against the same SQLite DB
            reloaded_engine = self._build_mock_engine(db_path)
            reloaded_app = create_app(engine=reloaded_engine)
            with TestClient(reloaded_app) as client2:
                detail_resp = client2.get(f"/api/v1/sessions/{sid}")
                self.assertEqual(detail_resp.status_code, 200)
                detail = detail_resp.json()
                self.assertEqual(detail["session"]["turn_count"], 2)
                self.assertEqual(len(detail["turns"]), 2)
                self.assertEqual(detail["turns"][1]["standalone_question"], "What SLA compliance terms are required under NIST SP 800-144?")
                self.assertEqual(detail["turns"][1]["source_chunk_ids"], ["NIST_SP_800-144_txt_00113"])
                self.assertTrue(any(f["key"] == "NIST SP 800-144" for f in detail["active_facts"]))

    def test_chat_stream_sse_events_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "api_stream.sqlite"
            engine = self._build_mock_engine(db_path)
            app = create_app(engine=engine)

            with TestClient(app) as client:
                sess = client.post("/api/v1/sessions", json={"title": "Stream Audit"}).json()
                sid = sess["session_id"]

                with client.stream(
                    "POST",
                    "/api/v1/chat/stream",
                    json={"question": "What does NIST SP 800-144 say about SLAs?", "session_id": sid},
                ) as resp:
                    self.assertEqual(resp.status_code, 200)
                    self.assertIn("text/event-stream", resp.headers["content-type"])
                    raw = resp.read().decode("utf-8")

                events = _parse_sse_events(raw)
                names = [name for name, _ in events]
                self.assertEqual(names[0], "session")
                self.assertEqual(names[1], "metadata")
                self.assertIn("token", names)
                self.assertEqual(names[-2], "memory")
                self.assertEqual(names[-1], "done")

                tokens = "".join(data["token"] for name, data in events if name == "token")
                self.assertEqual(tokens, "SLAs must define audits [Source 1].")

                detail = client.get(f"/api/v1/sessions/{sid}").json()
                self.assertEqual(len(detail["turns"]), 1)
                self.assertEqual(detail["turns"][0]["assistant"], "SLAs must define audits [Source 1].")

    def test_session_crud_clear_delete_and_404_handling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "api_sessions.sqlite"
            engine = self._build_mock_engine(db_path)
            app = create_app(engine=engine)

            with TestClient(app) as client:
                # Create session
                created = client.post("/api/v1/sessions", json={"title": "NIST Review"})
                self.assertEqual(created.status_code, 200)
                sid = created.json()["session_id"]
                self.assertEqual(created.json()["title"], "NIST Review")

                # Add a turn
                chat_resp = client.post(
                    "/api/v1/chat",
                    json={"question": "Explain NIST SP 800-53 AU-3.", "session_id": sid},
                )
                self.assertEqual(chat_resp.status_code, 200)

                # List sessions
                listed = client.get("/api/v1/sessions")
                self.assertEqual(listed.status_code, 200)
                self.assertTrue(any(s["session_id"] == sid and s["turn_count"] == 1 for s in listed.json()))

                # Rename session and verify persisted title without breaking delete/404 flow
                renamed = client.patch(
                    f"/api/v1/sessions/{sid}",
                    json={"title": "Renamed NIST Audit"},
                )
                self.assertEqual(renamed.status_code, 200)
                self.assertEqual(renamed.json()["title"], "Renamed NIST Audit")
                self.assertEqual(
                    client.get(f"/api/v1/sessions/{sid}").json()["session"]["title"],
                    "Renamed NIST Audit",
                )
                self.assertEqual(
                    client.patch(f"/api/v1/sessions/{sid}", json={"title": "   "}).status_code,
                    422,
                )

                # Clear session retains session row with 0 turns
                cleared = client.post(f"/api/v1/sessions/{sid}/clear")
                self.assertEqual(cleared.status_code, 200)
                self.assertEqual(cleared.json()["turn_count"], 0)
                detail_after_clear = client.get(f"/api/v1/sessions/{sid}").json()
                self.assertEqual(detail_after_clear["turns"], [])

                # Delete session removes it completely
                deleted = client.delete(f"/api/v1/sessions/{sid}")
                self.assertEqual(deleted.status_code, 200)
                self.assertEqual(deleted.json(), {"deleted": True, "session_id": sid})

                # Missing session returns 404 across GET / PATCH / POST clear / DELETE
                self.assertEqual(client.get(f"/api/v1/sessions/{sid}").status_code, 404)
                self.assertEqual(
                    client.patch(f"/api/v1/sessions/{sid}", json={"title": "Ghost"}).status_code,
                    404,
                )
                self.assertEqual(client.post(f"/api/v1/sessions/{sid}/clear").status_code, 404)
                self.assertEqual(client.delete(f"/api/v1/sessions/{sid}").status_code, 404)

    def test_blank_question_returns_422(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = self._build_mock_engine(Path(tmpdir) / "api_val.sqlite")
            app = create_app(engine=engine)
            with TestClient(app) as client:
                self.assertEqual(client.post("/api/v1/chat", json={"question": "   "}).status_code, 422)
                self.assertEqual(client.post("/api/v1/chat/stream", json={"question": ""}).status_code, 422)

    def test_chat_and_stream_apply_user_preferences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = self._build_mock_engine(Path(tmpdir) / "api_prefs.sqlite")
            app = create_app(engine=engine)
            prefs = {
                "detail_level": "Concise",
                "response_format": "TL;DR First",
                "focus_lens": "Hands-On Code",
                "custom_instructions": "Include verification steps.",
            }
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/chat",
                    json={"question": "What SLA clauses apply?", "preferences": prefs},
                )
                self.assertEqual(resp.status_code, 200)
                gen_prompt = engine.llm_provider.generate.call_args.args[0]
                self.assertIn("USER PREFERENCES", gen_prompt)
                self.assertIn("Concise", gen_prompt)
                self.assertIn("TL;DR First", gen_prompt)
                self.assertIn("Hands-On Code", gen_prompt)
                self.assertIn("Include verification steps.", gen_prompt)

                stream_resp = client.post(
                    "/api/v1/chat/stream",
                    json={"question": "Stream SLA clauses?", "preferences": prefs},
                )
                self.assertEqual(stream_resp.status_code, 200)
                stream_prompt = engine.llm_provider.stream.call_args.args[0]
                self.assertIn("USER PREFERENCES", stream_prompt)
                self.assertIn("Concise", stream_prompt)

    def test_recents_ordering_updates_when_older_session_receives_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = self._build_mock_engine(Path(tmpdir) / "api_order.sqlite")
            app = create_app(engine=engine)
            with TestClient(app) as client:
                c1 = client.post(
                    "/api/v1/chat",
                    json={"question": "First topic on NIST AU-3 audit logs"},
                ).json()
                sid1 = c1["session_id"]

                c2 = client.post(
                    "/api/v1/chat",
                    json={"question": "Second topic on NIST SP 800-207 Zero Trust"},
                ).json()
                sid2 = c2["session_id"]

                # Second session is most recent initially
                recents_before = client.get("/api/v1/sessions").json()
                self.assertEqual(recents_before[0]["session_id"], sid2)
                self.assertEqual(recents_before[1]["session_id"], sid1)

                # Replying to first session promotes it back to top of Recents
                client.post(
                    "/api/v1/chat",
                    json={"question": "Follow up on AU-3", "session_id": sid1},
                )
                recents_after = client.get("/api/v1/sessions").json()
                self.assertEqual(recents_after[0]["session_id"], sid1)
                self.assertEqual(recents_after[1]["session_id"], sid2)


if __name__ == "__main__":
    unittest.main()
