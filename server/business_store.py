"""Durable Server business records and audit ledger (WB-432).

This module deliberately owns only committed business state. Device execution
leases/events and object bytes are separate protocols introduced by WB-433 and
WB-436; their stable references terminate in the rows managed here.
"""
from __future__ import annotations

import base64
import json
import sqlite3
import time
from typing import Any

import db


_TABLES = {
    "business_sessions",
    "business_messages",
    "business_runs",
    "business_run_steps",
    "business_assistants",
    "business_channels",
    "business_automations",
    "business_assets",
}
_JSON_COLUMNS = {
    "trace", "usage", "model_snapshot", "plan", "permission_snapshot", "checkpoint",
    "required_capabilities", "request_snapshot",
    "payload", "experts", "skills", "connectors", "public_config",
    "preauthorized_permissions", "validation", "details",
}
_BOOL_COLUMNS = {"enabled"}


class IdempotencyConflict(ValueError):
    """The same idempotency key was reused with a different payload."""


class VersionConflict(ValueError):
    """An optimistic update targeted a stale record version."""


def _assert_table(table: str) -> None:
    if table not in _TABLES:
        raise ValueError(f"unsupported business table: {table}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result.pop("request_hash", None)
    for key in _JSON_COLUMNS & result.keys():
        value = result[key]
        if value is None:
            continue
        try:
            result[key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            result[key] = None
    for key in _BOOL_COLUMNS & result.keys():
        result[key] = bool(result[key])
    return result


def get_record(table: str, record_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    _assert_table(table)
    suffix = "" if include_deleted else " AND deleted_at=0"
    return decode_row(
        db.get_conn().execute(f"SELECT * FROM {table} WHERE id=?{suffix}", (record_id,)).fetchone()
    )


def _encode_cursor(value: float | int, record_id: str) -> str:
    raw = _json([value, record_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[float, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value, record_id = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return float(value), str(record_id)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


def list_scoped(
    table: str,
    *,
    account_id: str,
    project_id: str | None,
    limit: int,
    cursor: str = "",
    parent: tuple[str, str] | None = None,
    order_column: str = "updated_at",
    ascending: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """List a stable page visible to an account or under an authorized parent."""
    _assert_table(table)
    if order_column not in {"updated_at", "created_at", "sequence"}:
        raise ValueError("unsupported order column")
    where = ["t.deleted_at=0"] if table not in {"business_messages", "business_run_steps"} else []
    params: list[Any] = []
    if parent is not None:
        column, value = parent
        if column not in {"session_id", "run_id", "assistant_id"}:
            raise ValueError("unsupported parent column")
        where.append(f"t.{column}=?")
        params.append(value)
    elif project_id:
        where.append("t.project_id=?")
        params.append(project_id)
    else:
        where.append(
            "((t.project_id IS NULL AND t.owner_id=?) OR EXISTS ("
            "SELECT 1 FROM projects p LEFT JOIN project_members pm "
            "ON pm.project_id=p.id AND pm.account_id=? "
            "WHERE p.id=t.project_id AND (p.owner_id=? OR pm.account_id IS NOT NULL)))"
        )
        params.extend((account_id, account_id, account_id))
    if table == "business_runs":
        where.append(
            "EXISTS (SELECT 1 FROM business_sessions s "
            "WHERE s.id=t.session_id AND s.deleted_at=0)"
        )
    parsed = decode_cursor(cursor)
    direction = "ASC" if ascending else "DESC"
    if parsed is not None:
        value, record_id = parsed
        op = ">" if ascending else "<"
        where.append(f"(t.{order_column}{op}? OR (t.{order_column}=? AND t.id{op}?))")
        params.extend((value, value, record_id))
    rows = db.get_conn().execute(
        f"SELECT t.* FROM {table} t WHERE {' AND '.join(where) if where else '1=1'} "
        f"ORDER BY t.{order_column} {direction},t.id {direction} LIMIT ?",
        (*params, limit + 1),
    ).fetchall()
    page_rows = rows[:limit]
    next_cursor = ""
    if len(rows) > limit and page_rows:
        tail = page_rows[-1]
        next_cursor = _encode_cursor(tail[order_column], tail["id"])
    return [decode_row(row) or {} for row in page_rows], next_cursor


def _audit(
    conn: sqlite3.Connection,
    *,
    actor_id: str,
    owner_id: str,
    project_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO business_audit "
        "(id,actor_id,owner_id,project_id,action,entity_type,entity_id,details,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            db.new_uuid(), actor_id, owner_id, project_id, action, entity_type, entity_id,
            _json(details or {}), time.time(),
        ),
    )


def create_record(
    table: str,
    *,
    entity_type: str,
    actor_id: str,
    owner_id: str,
    project_id: str | None,
    fields: dict[str, Any],
    client_request_id: str = "",
    request_hash: str = "",
    record_id: str | None = None,
    sequence_parent: tuple[str, str] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create one record and audit row; return (record, duplicate)."""
    _assert_table(table)
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if client_request_id:
            existing = conn.execute(
                f"SELECT * FROM {table} WHERE owner_id=? AND client_request_id=?",
                (owner_id, client_request_id),
            ).fetchone()
            if existing is not None:
                if str(existing["request_hash"]) != request_hash:
                    raise IdempotencyConflict("idempotency key payload mismatch")
                conn.commit()
                return decode_row(existing) or {}, True
        values = dict(fields)
        if sequence_parent is not None:
            parent_column, parent_id = sequence_parent
            if parent_column not in {"session_id", "run_id"}:
                raise ValueError("unsupported sequence parent")
            values["sequence"] = int(conn.execute(
                f"SELECT COALESCE(MAX(sequence),0)+1 FROM {table} WHERE {parent_column}=?",
                (parent_id,),
            ).fetchone()[0])
        now = time.time()
        rid = record_id or db.new_uuid()
        values.update({"id": rid, "owner_id": owner_id, "created_at": now})
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "project_id" in columns:
            values["project_id"] = project_id
        if "updated_at" in columns:
            values["updated_at"] = now
        if "client_request_id" in columns:
            values["client_request_id"] = client_request_id
            values["request_hash"] = request_hash
        encoded: dict[str, Any] = {}
        for key, value in values.items():
            encoded[key] = _json(value) if key in _JSON_COLUMNS and value is not None else value
        names = list(encoded)
        conn.execute(
            f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
            tuple(encoded[name] for name in names),
        )
        _audit(
            conn, actor_id=actor_id, owner_id=owner_id, project_id=project_id,
            action="create", entity_type=entity_type, entity_id=rid,
            details={"client_request_id": client_request_id} if client_request_id else {},
        )
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
        conn.commit()
        return decode_row(row) or {}, False
    except Exception:
        conn.rollback()
        raise


def create_turn(
    *,
    actor_id: str,
    owner_id: str,
    project_id: str | None,
    session_id: str | None,
    session_title: str,
    session_kind: str,
    session_space: str | None,
    user_text: str,
    run_fields: dict[str, Any],
    client_request_id: str,
    request_hash: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool]:
    """Atomically create the Session/UserMessage/Run execution turn.

    A Desktop crash between three independent HTTP calls must never leave a
    message without a Run (or a queued Run without its input).  The Run's
    client_request_id is the turn idempotency key; retries return the exact
    committed graph.
    """
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM business_runs WHERE owner_id=? AND client_request_id=?",
            (owner_id, client_request_id),
        ).fetchone()
        if existing is not None:
            if str(existing["request_hash"]) != request_hash:
                raise IdempotencyConflict("idempotency key payload mismatch")
            session = conn.execute(
                "SELECT * FROM business_sessions WHERE id=? AND deleted_at=0",
                (existing["session_id"],),
            ).fetchone()
            message = conn.execute(
                "SELECT * FROM business_messages WHERE run_id=? AND role='user' ORDER BY sequence LIMIT 1",
                (existing["id"],),
            ).fetchone()
            if session is None or message is None:
                raise RuntimeError("committed turn graph is incomplete")
            conn.commit()
            return (
                decode_row(session) or {}, decode_row(message) or {},
                decode_row(existing) or {}, True,
            )

        now = time.time()
        sid = session_id
        if sid:
            session = conn.execute(
                "SELECT * FROM business_sessions WHERE id=? AND deleted_at=0", (sid,),
            ).fetchone()
            if session is None:
                raise KeyError(sid)
        else:
            sid = db.new_uuid()
            conn.execute(
                "INSERT INTO business_sessions "
                "(id,owner_id,project_id,title,kind,status,space,client_request_id,request_hash,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'running',?,?,?,?,?)",
                (
                    sid, owner_id, project_id, session_title, session_kind, session_space,
                    f"{client_request_id}:session", request_hash, now, now,
                ),
            )
            _audit(
                conn, actor_id=actor_id, owner_id=owner_id, project_id=project_id,
                action="create", entity_type="session", entity_id=sid,
                details={"turn_id": client_request_id},
            )
            session = conn.execute("SELECT * FROM business_sessions WHERE id=?", (sid,)).fetchone()

        rid = db.new_uuid()
        values = dict(run_fields)
        values.update({
            "id": rid, "session_id": sid, "owner_id": owner_id,
            "project_id": project_id, "status": "queued",
            "client_request_id": client_request_id, "request_hash": request_hash,
            "created_at": now, "updated_at": now,
        })
        encoded = {
            key: _json(value) if key in _JSON_COLUMNS and value is not None else value
            for key, value in values.items()
        }
        names = list(encoded)
        conn.execute(
            f"INSERT INTO business_runs ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
            tuple(encoded[name] for name in names),
        )
        _audit(
            conn, actor_id=actor_id, owner_id=owner_id, project_id=project_id,
            action="create", entity_type="run", entity_id=rid,
            details={"turn_id": client_request_id},
        )

        sequence = int(conn.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM business_messages WHERE session_id=?", (sid,),
        ).fetchone()[0])
        mid = db.new_uuid()
        conn.execute(
            "INSERT INTO business_messages "
            "(id,session_id,owner_id,run_id,role,content,actor_id,trace,sequence,client_request_id,request_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,'[]',?,?,?,?)",
            (
                mid, sid, owner_id, rid, "user", user_text, actor_id, sequence,
                f"{client_request_id}:message", request_hash, now,
            ),
        )
        _audit(
            conn, actor_id=actor_id, owner_id=owner_id, project_id=project_id,
            action="create", entity_type="message", entity_id=mid,
            details={"turn_id": client_request_id, "run_id": rid},
        )
        conn.execute(
            "UPDATE business_sessions SET status='running',updated_at=?,version=version+1 WHERE id=?",
            (now, sid),
        )
        session = conn.execute("SELECT * FROM business_sessions WHERE id=?", (sid,)).fetchone()
        message = conn.execute("SELECT * FROM business_messages WHERE id=?", (mid,)).fetchone()
        run = conn.execute("SELECT * FROM business_runs WHERE id=?", (rid,)).fetchone()
        conn.commit()
        return decode_row(session) or {}, decode_row(message) or {}, decode_row(run) or {}, False
    except Exception:
        conn.rollback()
        raise


def update_record(
    table: str,
    record_id: str,
    *,
    entity_type: str,
    actor_id: str,
    owner_id: str,
    project_id: str | None,
    expected_version: int,
    fields: dict[str, Any],
) -> dict[str, Any]:
    _assert_table(table)
    conn = db.get_conn()
    encoded = {
        key: _json(value) if key in _JSON_COLUMNS and value is not None else value
        for key, value in fields.items()
    }
    encoded["updated_at"] = time.time()
    assignments = ",".join(f"{key}=?" for key in encoded)
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = conn.execute(
            f"UPDATE {table} SET {assignments},version=version+1 "
            "WHERE id=? AND version=? AND deleted_at=0",
            (*encoded.values(), record_id, expected_version),
        )
        if result.rowcount != 1:
            exists = conn.execute(f"SELECT 1 FROM {table} WHERE id=? AND deleted_at=0", (record_id,)).fetchone()
            if exists is None:
                raise KeyError(record_id)
            raise VersionConflict("stale record version")
        _audit(
            conn, actor_id=actor_id, owner_id=owner_id, project_id=project_id,
            action="update", entity_type=entity_type, entity_id=record_id,
            details={"fields": sorted(fields), "from_version": expected_version},
        )
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
        conn.commit()
        return decode_row(row) or {}
    except Exception:
        conn.rollback()
        raise


def soft_delete(
    table: str,
    record_id: str,
    *,
    entity_type: str,
    actor_id: str,
    owner_id: str,
    project_id: str | None,
    expected_version: int,
) -> None:
    _assert_table(table)
    conn = db.get_conn()
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = conn.execute(
            f"UPDATE {table} SET deleted_at=?,updated_at=?,version=version+1 "
            "WHERE id=? AND version=? AND deleted_at=0",
            (now, now, record_id, expected_version),
        )
        if result.rowcount != 1:
            exists = conn.execute(f"SELECT 1 FROM {table} WHERE id=? AND deleted_at=0", (record_id,)).fetchone()
            if exists is None:
                raise KeyError(record_id)
            raise VersionConflict("stale record version")
        _audit(
            conn, actor_id=actor_id, owner_id=owner_id, project_id=project_id,
            action="delete", entity_type=entity_type, entity_id=record_id,
            details={"from_version": expected_version},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def list_audit(
    *, account_id: str, project_id: str | None, limit: int, cursor: str = "",
) -> tuple[list[dict[str, Any]], str]:
    where: list[str] = []
    params: list[Any] = []
    if project_id:
        where.append("a.project_id=?")
        params.append(project_id)
    else:
        where.append(
            "((a.project_id IS NULL AND a.owner_id=?) OR EXISTS ("
            "SELECT 1 FROM projects p LEFT JOIN project_members pm "
            "ON pm.project_id=p.id AND pm.account_id=? "
            "WHERE p.id=a.project_id AND (p.owner_id=? OR pm.account_id IS NOT NULL)))"
        )
        params.extend((account_id, account_id, account_id))
    parsed = decode_cursor(cursor)
    if parsed is not None:
        value, record_id = parsed
        where.append("(a.created_at<? OR (a.created_at=? AND a.id<?))")
        params.extend((value, value, record_id))
    rows = db.get_conn().execute(
        f"SELECT a.* FROM business_audit a WHERE {' AND '.join(where)} "
        "ORDER BY a.created_at DESC,a.id DESC LIMIT ?",
        (*params, limit + 1),
    ).fetchall()
    page_rows = rows[:limit]
    next_cursor = ""
    if len(rows) > limit and page_rows:
        next_cursor = _encode_cursor(page_rows[-1]["created_at"], page_rows[-1]["id"])
    return [decode_row(row) or {} for row in page_rows], next_cursor
