"""SQLite persistence.

Thin DAO over stdlib sqlite3 — no ORM. Chat streaming is the async hot path
(LLM over httpx); DB writes happen at the boundaries of a stream (session create,
message persist) and are quick, so synchronous sqlite calls are fine here.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Optional

from config import settings
from storage.models import (
    LOCAL_USER_ID,
    LOCAL_USER_NAME,
    Message,
    Role,
    Session,
    User,
)

_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def new_uuid() -> str:
    return str(uuid.uuid4())


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            plan TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            space TEXT,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            actor TEXT NOT NULL,
            trace TEXT NOT NULL DEFAULT '[]',
            usage TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_owner
            ON sessions(owner_id, updated_at DESC);
        """
    )
    conn.commit()
    _ensure_local_user()


def _ensure_local_user() -> None:
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE id=?", (LOCAL_USER_ID,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (id, name, role, plan) VALUES (?,?,?,?)",
            (LOCAL_USER_ID, LOCAL_USER_NAME, Role.OWNER.value, "体验版"),
        )
        conn.commit()


# ---- users --------------------------------------------------------------

def get_user(user_id: str) -> Optional[User]:
    row = get_conn().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    return User(id=row["id"], name=row["name"], role=Role(row["role"]), plan=row["plan"])


# ---- sessions -----------------------------------------------------------

def create_session(
    *,
    owner_id: str,
    title: str,
    kind: str = "chat",
    space: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Session:
    now = time.time()
    s = Session(
        id=new_uuid(),
        title=title[:120],
        owner_id=owner_id,
        project_id=project_id,
        space=space,
        kind=kind,
        status="idle",
        created_at=now,
        updated_at=now,
    )
    get_conn().execute(
        """INSERT INTO sessions (id,title,owner_id,project_id,space,kind,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (s.id, s.title, s.owner_id, s.project_id, s.space, s.kind, s.status, s.created_at, s.updated_at),
    )
    get_conn().commit()
    return s


def get_session(session_id: str) -> Optional[Session]:
    row = get_conn().execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def list_sessions(owner_id: str, space: Optional[str] = None) -> list[Session]:
    if space:
        rows = get_conn().execute(
            "SELECT * FROM sessions WHERE owner_id=? AND space=? ORDER BY updated_at DESC",
            (owner_id, space),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM sessions WHERE owner_id=? ORDER BY updated_at DESC",
            (owner_id,),
        ).fetchall()
    return [_row_to_session(r) for r in rows]


def touch_session(session_id: str, status: Optional[str] = None) -> None:
    if status is not None:
        get_conn().execute(
            "UPDATE sessions SET updated_at=?, status=? WHERE id=?",
            (time.time(), status, session_id),
        )
    else:
        get_conn().execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), session_id)
        )
    get_conn().commit()


def rename_session(session_id: str, title: str) -> None:
    get_conn().execute(
        "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
        (title[:120], time.time(), session_id),
    )
    get_conn().commit()


def delete_session(session_id: str) -> None:
    get_conn().execute("DELETE FROM sessions WHERE id=?", (session_id,))
    get_conn().commit()


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        title=row["title"],
        owner_id=row["owner_id"],
        project_id=row["project_id"],
        space=row["space"],
        kind=row["kind"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---- messages -----------------------------------------------------------

def add_message(
    *,
    session_id: str,
    role: str,
    content: str,
    actor: str,
    trace: Optional[list[dict[str, Any]]] = None,
    usage: Optional[dict[str, Any]] = None,
) -> Message:
    m = Message(
        id=new_uuid(),
        session_id=session_id,
        role=role,
        content=content,
        actor=actor,
        trace=trace or [],
        usage=usage,
        created_at=time.time(),
    )
    get_conn().execute(
        """INSERT INTO messages (id,session_id,role,content,actor,trace,usage,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            m.id,
            m.session_id,
            m.role,
            m.content,
            m.actor,
            json.dumps(m.trace, ensure_ascii=False),
            json.dumps(m.usage, ensure_ascii=False) if m.usage else None,
            m.created_at,
        ),
    )
    get_conn().commit()
    return m


def list_messages(session_id: str) -> list[Message]:
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    out: list[Message] = []
    for r in rows:
        out.append(
            Message(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                actor=r["actor"],
                trace=json.loads(r["trace"]) if r["trace"] else [],
                usage=json.loads(r["usage"]) if r["usage"] else None,
                created_at=r["created_at"],
            )
        )
    return out
