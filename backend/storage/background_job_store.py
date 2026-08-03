"""Durable owner-scoped background job state (WB-345)."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from storage import db

ACTIVE_STATUSES = {"queued", "running", "retry_wait"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def ensure_tables() -> None:
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS background_jobs (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            attempt INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            next_attempt_at REAL NOT NULL,
            lease_owner TEXT,
            lease_expires_at REAL,
            heartbeat_at REAL,
            error_code TEXT,
            error_message TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_background_jobs_owner_key
            ON background_jobs(owner_id,kind,idempotency_key);
        CREATE INDEX IF NOT EXISTS idx_background_jobs_due
            ON background_jobs(status,next_attempt_at);
        CREATE INDEX IF NOT EXISTS idx_background_jobs_entity
            ON background_jobs(owner_id,kind,entity_id,created_at DESC);
        """
    )
    conn.commit()


def _job(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    try:
        payload = json.loads(item.get("payload") or "{}")
        item["payload"] = payload if isinstance(payload, dict) else {}
    except (TypeError, json.JSONDecodeError):
        item["payload"] = {}
    return item


def enqueue(
    *, owner_id: str, kind: str, entity_id: str, idempotency_key: str,
    payload: dict[str, Any] | None = None, max_attempts: int = 3,
    next_attempt_at: float | None = None,
) -> tuple[dict[str, Any], bool]:
    owner = owner_id.strip()
    job_kind = kind.strip()[:80]
    entity = entity_id.strip()[:200]
    key = idempotency_key.strip()[:200]
    if not owner or not job_kind or not entity or not key:
        raise ValueError("background job scope and idempotency key are required")
    ensure_tables()
    now = time.time()
    job_id = str(uuid.uuid4())
    try:
        db.get_conn().execute(
            "INSERT INTO background_jobs "
            "(id,owner_id,kind,entity_id,payload,idempotency_key,status,attempt,max_attempts,"
            "next_attempt_at,created_at,updated_at) VALUES (?,?,?,?,?,?,'queued',0,?,?,?,?)",
            (
                job_id, owner, job_kind, entity,
                json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")), key,
                max(1, min(int(max_attempts), 10)),
                now if next_attempt_at is None else float(next_attempt_at), now, now,
            ),
        )
        db.get_conn().commit()
    except sqlite3.IntegrityError:
        db.get_conn().rollback()
        row = db.get_conn().execute(
            "SELECT * FROM background_jobs WHERE owner_id=? AND kind=? AND idempotency_key=?",
            (owner, job_kind, key),
        ).fetchone()
        if row:
            return _job(row) or {}, False
        raise
    return get(job_id) or {}, True


def get(job_id: str) -> dict[str, Any] | None:
    return _job(db.get_conn().execute(
        "SELECT * FROM background_jobs WHERE id=?", (job_id,),
    ).fetchone())


def get_for_entity(owner_id: str, kind: str, entity_id: str) -> dict[str, Any] | None:
    return _job(db.get_conn().execute(
        "SELECT * FROM background_jobs WHERE owner_id=? AND kind=? AND entity_id=? "
        "ORDER BY created_at DESC LIMIT 1",
        (owner_id, kind, entity_id),
    ).fetchone())


def list_due(now: float, limit: int) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT * FROM background_jobs WHERE status IN ('queued','retry_wait') "
        "AND next_attempt_at<=? ORDER BY next_attempt_at,created_at LIMIT ?",
        (float(now), max(1, min(int(limit), 100))),
    ).fetchall()
    return [_job(row) or {} for row in rows]


def health_summary(owner_id: str, now: float | None = None) -> dict[str, Any]:
    """Owner-scoped queue metadata only; payloads and entity identifiers never leave storage."""
    current = time.time() if now is None else float(now)
    rows = db.get_conn().execute(
        "SELECT status,COUNT(*) AS count FROM background_jobs WHERE owner_id=? GROUP BY status",
        (owner_id,),
    ).fetchall()
    counts = {str(row["status"]): int(row["count"]) for row in rows}
    due = db.get_conn().execute(
        """SELECT COUNT(*) AS count,MIN(next_attempt_at) AS oldest
           FROM background_jobs WHERE owner_id=? AND status IN ('queued','retry_wait')
           AND next_attempt_at<=?""",
        (owner_id, current),
    ).fetchone()
    return {
        "counts": counts,
        "due": int(due["count"] or 0),
        "oldest_due_at": float(due["oldest"]) if due["oldest"] is not None else None,
    }


def claim(job_id: str, lease_owner: str, now: float, lease_seconds: float) -> dict[str, Any] | None:
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status,next_attempt_at FROM background_jobs WHERE id=?", (job_id,),
        ).fetchone()
        if not row or row["status"] not in {"queued", "retry_wait"} or float(row["next_attempt_at"]) > now:
            conn.rollback()
            return None
        updated = conn.execute(
            "UPDATE background_jobs SET status='running',attempt=attempt+1,lease_owner=?,"
            "lease_expires_at=?,heartbeat_at=?,started_at=COALESCE(started_at,?),updated_at=?,"
            "error_code=NULL,error_message=NULL WHERE id=? AND status IN ('queued','retry_wait')",
            (lease_owner, now + max(1.0, lease_seconds), now, now, now, job_id),
        )
        if updated.rowcount != 1:
            conn.rollback()
            return None
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get(job_id)


def heartbeat(job_id: str, lease_owner: str, now: float, lease_seconds: float) -> bool:
    updated = db.get_conn().execute(
        "UPDATE background_jobs SET heartbeat_at=?,lease_expires_at=?,updated_at=? "
        "WHERE id=? AND status='running' AND lease_owner=?",
        (now, now + max(1.0, lease_seconds), now, job_id, lease_owner),
    )
    db.get_conn().commit()
    return updated.rowcount == 1


def finish_success(job_id: str, lease_owner: str) -> dict[str, Any] | None:
    now = time.time()
    db.get_conn().execute(
        "UPDATE background_jobs SET status='succeeded',lease_owner=NULL,lease_expires_at=NULL,"
        "heartbeat_at=NULL,error_code=NULL,error_message=NULL,finished_at=?,updated_at=? "
        "WHERE id=? AND status='running' AND lease_owner=?",
        (now, now, job_id, lease_owner),
    )
    db.get_conn().commit()
    return get(job_id)


def finish_failure(
    job_id: str, lease_owner: str, *, error_code: str, error_message: str,
    retry_at: float, force_terminal: bool = False,
) -> dict[str, Any] | None:
    job = get(job_id)
    if not job or job["status"] != "running" or job.get("lease_owner") != lease_owner:
        return job
    now = time.time()
    terminal = force_terminal or int(job["attempt"]) >= int(job["max_attempts"])
    status = "failed" if terminal else "retry_wait"
    db.get_conn().execute(
        "UPDATE background_jobs SET status=?,next_attempt_at=?,lease_owner=NULL,"
        "lease_expires_at=NULL,heartbeat_at=NULL,error_code=?,error_message=?,"
        "finished_at=?,updated_at=? WHERE id=? AND status='running' AND lease_owner=?",
        (
            status, float(retry_at), error_code[:120], error_message[:1000],
            now if terminal else None, now, job_id, lease_owner,
        ),
    )
    db.get_conn().commit()
    return get(job_id)


def release(job_id: str, lease_owner: str, reason: str = "worker_stopped") -> dict[str, Any] | None:
    """Return a controlled-shutdown attempt to the queue without consuming its retry budget."""
    now = time.time()
    db.get_conn().execute(
        "UPDATE background_jobs SET status='queued',attempt=MAX(0,attempt-1),next_attempt_at=?,"
        "lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,error_code=?,error_message=?,"
        "updated_at=? WHERE id=? AND status='running' AND lease_owner=?",
        (now, reason[:120], reason[:1000], now, job_id, lease_owner),
    )
    db.get_conn().commit()
    return get(job_id)


def cancel(job_id: str) -> dict[str, Any] | None:
    now = time.time()
    db.get_conn().execute(
        "UPDATE background_jobs SET status='cancelled',lease_owner=NULL,lease_expires_at=NULL,"
        "heartbeat_at=NULL,error_code='cancelled_by_user',error_message='cancelled_by_user',"
        "finished_at=?,updated_at=? WHERE id=? AND status IN ('queued','running','retry_wait')",
        (now, now, job_id),
    )
    db.get_conn().commit()
    return get(job_id)


def recover_expired(now: float) -> list[dict[str, Any]]:
    """Recover only expired leases; a live worker keeps extending its own lease."""
    conn = db.get_conn()
    recovered: list[str] = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id,attempt,max_attempts FROM background_jobs WHERE status='running' "
            "AND (lease_expires_at IS NULL OR lease_expires_at<=?)",
            (float(now),),
        ).fetchall()
        for row in rows:
            terminal = int(row["attempt"]) >= int(row["max_attempts"])
            conn.execute(
                "UPDATE background_jobs SET status=?,next_attempt_at=?,lease_owner=NULL,"
                "lease_expires_at=NULL,heartbeat_at=NULL,error_code='worker_restarted',"
                "error_message='background worker lease expired after process interruption',"
                "finished_at=?,updated_at=? WHERE id=? AND status='running'",
                (
                    "failed" if terminal else "retry_wait", float(now),
                    float(now) if terminal else None, float(now), row["id"],
                ),
            )
            recovered.append(str(row["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return [job for job_id in recovered if (job := get(job_id)) is not None]
