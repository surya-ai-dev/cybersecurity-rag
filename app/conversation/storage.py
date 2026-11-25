"""SQLite persistent store for multi-turn Cybersecurity RAG memory."""

from array import array
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import List, Optional, Sequence, Tuple, Union
import uuid

from app.core.models import MemoryFact, Message, SessionMetadata


def _utc_now_iso() -> str:
    """Return current UTC timestamp formatted as ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def _make_session_title(first_question: str, max_len: int = 56) -> str:
    """Derive a concise session title from the opening user question."""
    cleaned = " ".join(first_question.strip().split())
    if not cleaned:
        return "New Session"
    if len(cleaned) <= max_len:
        return cleaned
    clipped = cleaned[: max_len - 1]
    last_space = clipped.rfind(" ")
    base = clipped[:last_space] if last_space > max_len // 3 else clipped
    return f"{base.rstrip()}…"


class SQLiteMemoryStore:
    """Thread-safe SQLite repository for sessions, turns, facts, and episodic vectors."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        raw_path = str(db_path)
        self._is_memory = raw_path == ":memory:"
        if self._is_memory:
            self.db_path: Union[str, Path] = ":memory:"
            db_target = ":memory:"
        else:
            path_obj = Path(db_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = path_obj
            db_target = str(path_obj)

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            db_target,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteMemoryStore connection is closed.")
        return self._conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._require_conn()
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New Session',
                    summary TEXT NOT NULL DEFAULT '',
                    last_summarized_turn_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    user_message TEXT NOT NULL,
                    standalone_question TEXT,
                    assistant_message TEXT NOT NULL,
                    source_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_turns_session_idx
                    ON turns(session_id, turn_index);

                CREATE TABLE IF NOT EXISTS memory_facts (
                    fact_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    fact_value TEXT NOT NULL,
                    source_turn INTEGER,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique
                    ON memory_facts(session_id, category, fact_key);

                CREATE TABLE IF NOT EXISTS episodic_embeddings (
                    fact_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    embedding_blob BLOB NOT NULL,
                    dim INTEGER NOT NULL,
                    FOREIGN KEY (fact_id) REFERENCES memory_facts(fact_id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()

    def create_session(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> SessionMetadata:
        """Create a new session (or return existing metadata if session_id exists)."""
        sid = session_id or str(uuid.uuid4())
        session_title = title.strip() if title and title.strip() else "New Session"
        now = _utc_now_iso()

        with self._lock:
            conn = self._require_conn()
            existing = self.get_session(sid)
            if existing is not None:
                return existing

            conn.execute(
                """
                INSERT INTO sessions (session_id, title, summary, last_summarized_turn_index, created_at, updated_at)
                VALUES (?, ?, '', 0, ?, ?)
                """,
                (sid, session_title, now, now),
            )
            conn.commit()
            return SessionMetadata(
                session_id=sid,
                title=session_title,
                summary="",
                turn_count=0,
                created_at=now,
                updated_at=now,
            )

    def get_session(self, session_id: str) -> Optional[SessionMetadata]:
        """Fetch session metadata including total persisted turn count."""
        with self._lock:
            conn = self._require_conn()
            row = conn.execute(
                """
                SELECT s.session_id, s.title, s.summary, s.created_at, s.updated_at,
                       COUNT(t.id) AS turn_count
                FROM sessions s
                LEFT JOIN turns t ON s.session_id = t.session_id
                WHERE s.session_id = ?
                GROUP BY s.session_id
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return SessionMetadata(
                session_id=str(row["session_id"]),
                title=str(row["title"]),
                summary=str(row["summary"]),
                turn_count=int(row["turn_count"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )

    def list_sessions(self, limit: int = 20) -> List[SessionMetadata]:
        """List persisted sessions ordered by most recently updated first."""
        with self._lock:
            conn = self._require_conn()
            rows = conn.execute(
                """
                SELECT s.session_id, s.title, s.summary, s.created_at, s.updated_at,
                       COUNT(t.id) AS turn_count
                FROM sessions s
                LEFT JOIN turns t ON s.session_id = t.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC, s.rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                SessionMetadata(
                    session_id=str(row["session_id"]),
                    title=str(row["title"]),
                    summary=str(row["summary"]),
                    turn_count=int(row["turn_count"]),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
                for row in rows
            ]

    def append_turn(self, session_id: str, message: Message) -> int:
        """Persist a conversation turn, auto-creating the session if absent."""
        now = message.timestamp or _utc_now_iso()
        chunk_ids_json = json.dumps(list(message.source_chunk_ids or []))

        with self._lock:
            conn = self._require_conn()
            session_row = conn.execute(
                "SELECT title FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if session_row is None:
                auto_title = _make_session_title(message.user)
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, title, summary, last_summarized_turn_index, created_at, updated_at)
                    VALUES (?, ?, '', 0, ?, ?)
                    """,
                    (session_id, auto_title, now, now),
                )
            elif session_row["title"] in ("New Session", "New chat", "") and message.user.strip():
                conn.execute(
                    "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                    (_make_session_title(message.user), now, session_id),
                )

            max_row = conn.execute(
                "SELECT COALESCE(MAX(turn_index), 0) AS max_idx FROM turns WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            next_index = int(max_row["max_idx"]) + 1 if max_row is not None else 1

            conn.execute(
                """
                INSERT INTO turns (
                    session_id,
                    turn_index,
                    user_message,
                    standalone_question,
                    assistant_message,
                    source_chunk_ids_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    next_index,
                    message.user,
                    message.standalone_question,
                    message.assistant,
                    chunk_ids_json,
                    now,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()
            return next_index

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        raw_chunks = row["source_chunk_ids_json"]
        try:
            parsed_chunks = json.loads(raw_chunks) if raw_chunks else []
            chunk_ids = [str(c) for c in parsed_chunks] if isinstance(parsed_chunks, list) else []
        except Exception:
            chunk_ids = []

        return Message(
            user=str(row["user_message"]),
            assistant=str(row["assistant_message"]),
            timestamp=str(row["created_at"]),
            standalone_question=row["standalone_question"],
            source_chunk_ids=chunk_ids,
            turn_index=int(row["turn_index"]),
        )

    def get_recent_turns(self, session_id: str, limit: int = 6) -> List[Message]:
        """Return up to `limit` most recent turns for a session in chronological order."""
        if limit <= 0:
            return []
        with self._lock:
            conn = self._require_conn()
            rows = conn.execute(
                """
                SELECT turn_index, user_message, standalone_question,
                       assistant_message, source_chunk_ids_json, created_at
                FROM turns
                WHERE session_id = ?
                ORDER BY turn_index DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            rows_chrono = list(reversed(rows))
            return [self._row_to_message(row) for row in rows_chrono]

    def get_session_turns(self, session_id: str, limit: int = 100) -> List[Message]:
        """Return up to `limit` chronological turns for a session starting from turn 1."""
        if limit <= 0:
            return []
        with self._lock:
            conn = self._require_conn()
            rows = conn.execute(
                """
                SELECT turn_index, user_message, standalone_question,
                       assistant_message, source_chunk_ids_json, created_at
                FROM turns
                WHERE session_id = ?
                ORDER BY turn_index ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            return [self._row_to_message(row) for row in rows]

    def get_unsummarized_turns(
        self,
        session_id: str,
        up_to_turn_index: Optional[int] = None,
    ) -> List[Message]:
        """Return turns after last_summarized_turn_index (optionally bounded above)."""
        with self._lock:
            conn = self._require_conn()
            session_row = conn.execute(
                "SELECT last_summarized_turn_index FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                return []

            last_summarized = int(session_row["last_summarized_turn_index"])
            if up_to_turn_index is not None:
                rows = conn.execute(
                    """
                    SELECT turn_index, user_message, standalone_question,
                           assistant_message, source_chunk_ids_json, created_at
                    FROM turns
                    WHERE session_id = ? AND turn_index > ? AND turn_index <= ?
                    ORDER BY turn_index ASC
                    """,
                    (session_id, last_summarized, up_to_turn_index),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT turn_index, user_message, standalone_question,
                           assistant_message, source_chunk_ids_json, created_at
                    FROM turns
                    WHERE session_id = ? AND turn_index > ?
                    ORDER BY turn_index ASC
                    """,
                    (session_id, last_summarized),
                ).fetchall()
            return [self._row_to_message(row) for row in rows]

    def update_summary(
        self,
        session_id: str,
        summary: str,
        last_summarized_turn_index: Optional[int] = None,
    ) -> None:
        """Persist updated rolling summary and optionally advance last_summarized_turn_index."""
        now = _utc_now_iso()
        with self._lock:
            conn = self._require_conn()
            if last_summarized_turn_index is not None:
                conn.execute(
                    """
                    UPDATE sessions
                    SET summary = ?, last_summarized_turn_index = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (summary, last_summarized_turn_index, now, session_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE sessions
                    SET summary = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (summary, now, session_id),
                )
            conn.commit()

    def upsert_fact(
        self,
        fact: MemoryFact,
        embedding: Optional[Sequence[float]] = None,
    ) -> None:
        """Insert or update a MemoryFact deduplicated by (session_id, category, key)."""
        now = fact.updated_at or _utc_now_iso()
        with self._lock:
            conn = self._require_conn()
            existing_session = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (fact.session_id,),
            ).fetchone()
            if existing_session is None:
                self.create_session(session_id=fact.session_id)

            conn.execute(
                """
                INSERT INTO memory_facts (
                    fact_id, session_id, category, fact_key, fact_value,
                    source_turn, confidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, category, fact_key) DO UPDATE SET
                    fact_value = excluded.fact_value,
                    source_turn = excluded.source_turn,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (
                    fact.fact_id,
                    fact.session_id,
                    fact.category,
                    fact.key,
                    fact.value,
                    fact.source_turn,
                    fact.confidence,
                    now,
                ),
            )

            if embedding is not None:
                row = conn.execute(
                    """
                    SELECT fact_id FROM memory_facts
                    WHERE session_id = ? AND category = ? AND fact_key = ?
                    """,
                    (fact.session_id, fact.category, fact.key),
                ).fetchone()
                effective_fact_id = str(row["fact_id"]) if row is not None else fact.fact_id
                vec_bytes = array("f", [float(x) for x in embedding]).tobytes()
                conn.execute(
                    """
                    INSERT INTO episodic_embeddings (fact_id, session_id, embedding_blob, dim)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(fact_id) DO UPDATE SET
                        embedding_blob = excluded.embedding_blob,
                        dim = excluded.dim
                    """,
                    (effective_fact_id, fact.session_id, vec_bytes, len(embedding)),
                )

            conn.commit()

    def _row_to_fact(self, row: sqlite3.Row) -> MemoryFact:
        return MemoryFact(
            fact_id=str(row["fact_id"]),
            session_id=str(row["session_id"]),
            category=str(row["category"]),
            key=str(row["fact_key"]),
            value=str(row["fact_value"]),
            source_turn=int(row["source_turn"]) if row["source_turn"] is not None else None,
            confidence=float(row["confidence"]),
            updated_at=str(row["updated_at"]),
        )

    def get_facts(
        self,
        session_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[MemoryFact]:
        """Fetch stored MemoryFact records filtered optionally by session_id and/or category."""
        clauses: List[str] = []
        params: List[str] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT fact_id, session_id, category, fact_key, fact_value,
                   source_turn, confidence, updated_at
            FROM memory_facts
            {where_sql}
            ORDER BY updated_at DESC, rowid DESC
        """
        with self._lock:
            conn = self._require_conn()
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._row_to_fact(row) for row in rows]

    def get_fact_embeddings(
        self,
        session_id: Optional[str] = None,
    ) -> List[Tuple[MemoryFact, bytes, int]]:
        """Return persisted facts alongside serialized float32 embedding blobs."""
        with self._lock:
            conn = self._require_conn()
            if session_id is not None:
                rows = conn.execute(
                    """
                    SELECT f.fact_id, f.session_id, f.category, f.fact_key, f.fact_value,
                           f.source_turn, f.confidence, f.updated_at,
                           e.embedding_blob, e.dim
                    FROM memory_facts f
                    INNER JOIN episodic_embeddings e ON f.fact_id = e.fact_id
                    WHERE f.session_id = ?
                    ORDER BY f.updated_at DESC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT f.fact_id, f.session_id, f.category, f.fact_key, f.fact_value,
                           f.source_turn, f.confidence, f.updated_at,
                           e.embedding_blob, e.dim
                    FROM memory_facts f
                    INNER JOIN episodic_embeddings e ON f.fact_id = e.fact_id
                    ORDER BY f.updated_at DESC
                    """
                ).fetchall()
            return [
                (self._row_to_fact(row), bytes(row["embedding_blob"]), int(row["dim"]))
                for row in rows
            ]

    def rename_session(self, session_id: str, title: str) -> Optional[SessionMetadata]:
        """Update the persisted title for an existing session without altering activity order."""
        clean_title = " ".join(title.strip().split())[:120]
        if not clean_title:
            raise ValueError("Session title cannot be empty.")
        with self._lock:
            conn = self._require_conn()
            cur = conn.execute(
                "UPDATE sessions SET title = ? WHERE session_id = ?",
                (clean_title, session_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
            return self.get_session(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete a session and cascade-remove its turns, facts, and embeddings."""
        with self._lock:
            conn = self._require_conn()
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection cleanly."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "SQLiteMemoryStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
