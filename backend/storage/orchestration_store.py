"""Durable local-only multi-agent orchestration state (WB-258)."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from storage import db


def ensure_tables() -> None:
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orchestrations (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            team_name TEXT NOT NULL,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT,
            max_nodes INTEGER NOT NULL,
            max_parallel INTEGER NOT NULL,
            max_total_tokens INTEGER NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            artifact_id TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            ended_at REAL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_orchestrations_owner_key
            ON orchestrations(owner_id,idempotency_key) WHERE idempotency_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_orchestrations_owner_created
            ON orchestrations(owner_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS orchestration_nodes (
            id TEXT PRIMARY KEY,
            orchestration_id TEXT NOT NULL,
            node_key TEXT NOT NULL,
            title TEXT NOT NULL,
            role TEXT NOT NULL,
            expert_slug TEXT NOT NULL,
            instruction TEXT NOT NULL,
            depends_on TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            session_id TEXT,
            run_id TEXT,
            output TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            started_at REAL,
            ended_at REAL,
            UNIQUE(orchestration_id,node_key),
            FOREIGN KEY(orchestration_id) REFERENCES orchestrations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_orchestration_nodes_parent
            ON orchestration_nodes(orchestration_id,created_at);
        CREATE TABLE IF NOT EXISTS orchestration_attempts (
            id TEXT PRIMARY KEY,
            orchestration_id TEXT NOT NULL,
            node_key TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            ended_at REAL,
            UNIQUE(orchestration_id,node_key,attempt),
            FOREIGN KEY(orchestration_id) REFERENCES orchestrations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_orchestration_attempts_parent
            ON orchestration_attempts(orchestration_id,node_key,attempt);
        """
    )
    # A process crash cannot leave a run looking active forever.
    now = time.time()
    conn.execute(
        "UPDATE orchestrations SET status='failed',error='process_restarted',ended_at=?,updated_at=? "
        "WHERE status IN ('planning','running','reviewing')",
        (now, now),
    )
    conn.execute(
        "UPDATE orchestration_nodes SET status='failed',error='process_restarted',ended_at=? "
        "WHERE status='running'",
        (now,),
    )
    conn.execute(
        "UPDATE orchestration_attempts SET status='failed',error='process_restarted',ended_at=? "
        "WHERE status='running'",
        (now,),
    )
    conn.commit()


def _loads(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _node(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["depends_on"] = _loads(item["depends_on"])
    item["attempts"] = list_attempts(item["orchestration_id"], item["node_key"])
    return item


def _orchestration(row: Any, *, include_nodes: bool = True) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["cancel_requested"] = bool(item["cancel_requested"])
    item["nodes"] = list_nodes(item["id"]) if include_nodes else []
    return item


def create(
    *, owner_id: str, project_id: str | None, team_name: str, goal: str,
    idempotency_key: str | None, max_nodes: int, max_parallel: int, max_total_tokens: int,
) -> tuple[dict[str, Any], bool]:
    key = (idempotency_key or "").strip()[:200] or None
    if key:
        existing = db.get_conn().execute(
            "SELECT * FROM orchestrations WHERE owner_id=? AND idempotency_key=?", (owner_id, key),
        ).fetchone()
        if existing:
            return _orchestration(existing) or {}, False
    oid = str(uuid.uuid4())
    now = time.time()
    try:
        db.get_conn().execute(
            "INSERT INTO orchestrations "
            "(id,owner_id,project_id,team_name,goal,status,idempotency_key,max_nodes,max_parallel,max_total_tokens,created_at,updated_at) "
            "VALUES (?,?,?,?,?,'planning',?,?,?,?,?,?)",
            (oid, owner_id, project_id, team_name, goal, key, max_nodes, max_parallel,
             max_total_tokens, now, now),
        )
        db.get_conn().commit()
    except Exception:
        db.get_conn().rollback()
        if key:
            row = db.get_conn().execute(
                "SELECT * FROM orchestrations WHERE owner_id=? AND idempotency_key=?", (owner_id, key),
            ).fetchone()
            if row:
                return _orchestration(row) or {}, False
        raise
    return get(oid, owner_id) or {}, True


def get(orchestration_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
    if owner_id:
        row = db.get_conn().execute(
            "SELECT * FROM orchestrations WHERE id=? AND owner_id=?", (orchestration_id, owner_id),
        ).fetchone()
    else:
        row = db.get_conn().execute("SELECT * FROM orchestrations WHERE id=?", (orchestration_id,)).fetchone()
    return _orchestration(row)


def list_for(owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT * FROM orchestrations WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
        (owner_id, max(1, min(limit, 200))),
    ).fetchall()
    return [_orchestration(row, include_nodes=False) or {} for row in rows]


def set_status(orchestration_id: str, status: str, *, error: str = "", artifact_id: str | None = None) -> None:
    if status not in {"planning", "running", "reviewing", "completed", "failed", "cancelled"}:
        raise ValueError("invalid orchestration status")
    now = time.time()
    terminal = now if status in {"completed", "failed", "cancelled"} else None
    db.get_conn().execute(
        "UPDATE orchestrations SET status=?,error=?,artifact_id=COALESCE(?,artifact_id),"
        "ended_at=COALESCE(?,ended_at),updated_at=? WHERE id=?",
        (status, error[:1000], artifact_id, terminal, now, orchestration_id),
    )
    db.get_conn().commit()


def request_cancel(orchestration_id: str) -> None:
    db.get_conn().execute(
        "UPDATE orchestrations SET cancel_requested=1,updated_at=? WHERE id=?",
        (time.time(), orchestration_id),
    )
    db.get_conn().commit()


def add_node(
    orchestration_id: str, *, node_key: str, title: str, role: str, expert_slug: str,
    instruction: str, depends_on: list[str], status: str = "pending",
) -> dict[str, Any]:
    node_id = str(uuid.uuid4())
    db.get_conn().execute(
        "INSERT INTO orchestration_nodes "
        "(id,orchestration_id,node_key,title,role,expert_slug,instruction,depends_on,status,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (node_id, orchestration_id, node_key, title[:160], role[:80], expert_slug[:120],
         instruction[:12000], json.dumps(depends_on, ensure_ascii=False), status, time.time()),
    )
    db.get_conn().commit()
    return get_node(orchestration_id, node_key) or {}


def get_node(orchestration_id: str, node_key: str) -> dict[str, Any] | None:
    row = db.get_conn().execute(
        "SELECT * FROM orchestration_nodes WHERE orchestration_id=? AND node_key=?",
        (orchestration_id, node_key),
    ).fetchone()
    return _node(row) if row else None


def list_nodes(orchestration_id: str) -> list[dict[str, Any]]:
    return [_node(row) for row in db.get_conn().execute(
        "SELECT * FROM orchestration_nodes WHERE orchestration_id=? ORDER BY created_at",
        (orchestration_id,),
    ).fetchall()]


def start_node(orchestration_id: str, node_key: str, session_id: str) -> None:
    db.get_conn().execute(
        "UPDATE orchestration_nodes SET status='running',session_id=?,started_at=? "
        "WHERE orchestration_id=? AND node_key=? AND status='pending'",
        (session_id, time.time(), orchestration_id, node_key),
    )
    db.get_conn().commit()


def start_attempt(orchestration_id: str, node_key: str, session_id: str) -> dict[str, Any]:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT COALESCE(MAX(attempt),0)+1 AS n FROM orchestration_attempts "
        "WHERE orchestration_id=? AND node_key=?", (orchestration_id, node_key),
    ).fetchone()
    attempt = int(row["n"])
    attempt_id = str(uuid.uuid4())
    now = time.time()
    conn.execute(
        "INSERT INTO orchestration_attempts "
        "(id,orchestration_id,node_key,attempt,session_id,status,created_at) "
        "VALUES (?,?,?,?,?,'running',?)",
        (attempt_id, orchestration_id, node_key, attempt, session_id, now),
    )
    conn.execute(
        "UPDATE orchestration_nodes SET status='running',session_id=?,started_at=COALESCE(started_at,?),"
        "ended_at=NULL WHERE orchestration_id=? AND node_key=?",
        (session_id, now, orchestration_id, node_key),
    )
    conn.commit()
    return {"id": attempt_id, "attempt": attempt}


def finish_attempt(
    attempt_id: str, *, status: str, run_id: str | None, error: str = "",
    prompt_tokens: int = 0, completion_tokens: int = 0,
) -> None:
    if status not in {"completed", "failed", "cancelled"}:
        raise ValueError("invalid attempt status")
    db.get_conn().execute(
        "UPDATE orchestration_attempts SET status=?,run_id=?,error=?,prompt_tokens=?,"
        "completion_tokens=?,ended_at=? WHERE id=?",
        (status, run_id, error[:2000], max(0, prompt_tokens), max(0, completion_tokens),
         time.time(), attempt_id),
    )
    db.get_conn().commit()


def list_attempts(orchestration_id: str, node_key: str) -> list[dict[str, Any]]:
    return [dict(row) for row in db.get_conn().execute(
        "SELECT * FROM orchestration_attempts WHERE orchestration_id=? AND node_key=? ORDER BY attempt",
        (orchestration_id, node_key),
    ).fetchall()]


def reset_node(orchestration_id: str, node_key: str) -> None:
    db.get_conn().execute(
        "UPDATE orchestration_nodes SET status='pending',output='',error='',ended_at=NULL "
        "WHERE orchestration_id=? AND node_key=?",
        (orchestration_id, node_key),
    )
    db.get_conn().commit()


def finish_node(
    orchestration_id: str, node_key: str, *, status: str, run_id: str | None,
    output: str = "", error: str = "", prompt_tokens: int = 0, completion_tokens: int = 0,
) -> None:
    if status not in {"completed", "failed", "skipped", "cancelled"}:
        raise ValueError("invalid node status")
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        attempt_totals = conn.execute(
            "SELECT COUNT(*),COALESCE(SUM(prompt_tokens),0),COALESCE(SUM(completion_tokens),0) "
            "FROM orchestration_attempts WHERE orchestration_id=? AND node_key=?",
            (orchestration_id, node_key),
        ).fetchone()
        if attempt_totals[0]:
            prompt_tokens, completion_tokens = attempt_totals[1], attempt_totals[2]
        conn.execute(
            "UPDATE orchestration_nodes SET status=?,run_id=?,output=?,error=?,prompt_tokens=?,"
            "completion_tokens=?,ended_at=? WHERE orchestration_id=? AND node_key=?",
            (status, run_id, output[:100000], error[:2000], max(0, prompt_tokens),
             max(0, completion_tokens), time.time(), orchestration_id, node_key),
        )
        totals = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0),COALESCE(SUM(completion_tokens),0) "
            "FROM orchestration_nodes WHERE orchestration_id=?", (orchestration_id,),
        ).fetchone()
        conn.execute(
            "UPDATE orchestrations SET prompt_tokens=?,completion_tokens=?,updated_at=? WHERE id=?",
            (totals[0], totals[1], time.time(), orchestration_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
