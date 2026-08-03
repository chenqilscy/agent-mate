"""Scoped service identities and durable device relay persistence (WB-361)."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from typing import Any

import db
from config import settings

SERVICE_SCOPES = {"relay:write", "relay:read"}
_TOKEN_RE = re.compile(r"^ams_([0-9a-f-]{36})\.([A-Za-z0-9_-]{32,})$")
_DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,119}$")
_EVENT_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_TERMINAL = ("succeeded", "failed", "dead_letter")
_cleanup_state: dict[str, Any] = {
    "last_run_at": None, "payloads_tombstoned": 0, "rows_deleted": 0,
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "owner_id": row["owner_id"], "name": row["name"],
        "scopes": json.loads(row["scopes"] or "[]"), "token_hint": row["token_hint"],
        "created_at": row["created_at"], "rotated_at": row["rotated_at"],
        "revoked_at": row["revoked_at"],
    }


def _issue_token(account_id: str) -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    token = f"ams_{account_id}.{secret}"
    return token, _hash(token), token[-6:]


def create_service_account(owner_id: str, name: str, scopes: list[str]) -> tuple[dict, str]:
    clean_scopes = sorted(set(scopes))
    if not clean_scopes or any(scope not in SERVICE_SCOPES for scope in clean_scopes):
        raise ValueError("invalid service account scopes")
    account_id = db.new_uuid()
    token, token_hash, hint = _issue_token(account_id)
    now = time.time()
    try:
        db.get_conn().execute(
            "INSERT INTO service_accounts "
            "(id,owner_id,name,scopes,token_hash,token_hint,created_at) VALUES (?,?,?,?,?,?,?)",
            (account_id, owner_id, name, json.dumps(clean_scopes), token_hash, hint, now),
        )
        db.get_conn().commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("service account name already exists") from exc
    return get_service_account(account_id, owner_id) or {}, token


def get_service_account(account_id: str, owner_id: str | None = None) -> dict | None:
    sql = "SELECT * FROM service_accounts WHERE id=?"
    values: tuple[Any, ...] = (account_id,)
    if owner_id is not None:
        sql += " AND owner_id=?"
        values += (owner_id,)
    row = db.get_conn().execute(sql, values).fetchone()
    return _public(row) if row else None


def list_service_accounts(owner_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        "SELECT * FROM service_accounts WHERE owner_id=? ORDER BY created_at DESC", (owner_id,),
    ).fetchall()
    return [_public(row) for row in rows]


def rotate_service_account(account_id: str, owner_id: str) -> tuple[dict, str] | None:
    if get_service_account(account_id, owner_id) is None:
        return None
    token, token_hash, hint = _issue_token(account_id)
    now = time.time()
    db.get_conn().execute(
        "UPDATE service_accounts SET token_hash=?,token_hint=?,rotated_at=?,revoked_at=NULL "
        "WHERE id=? AND owner_id=?",
        (token_hash, hint, now, account_id, owner_id),
    )
    db.get_conn().commit()
    return get_service_account(account_id, owner_id) or {}, token


def revoke_service_account(account_id: str, owner_id: str) -> bool:
    cur = db.get_conn().execute(
        "UPDATE service_accounts SET revoked_at=? WHERE id=? AND owner_id=? AND revoked_at IS NULL",
        (time.time(), account_id, owner_id),
    )
    db.get_conn().commit()
    return cur.rowcount > 0


def resolve_service_token(token: str, required_scope: str | None = None) -> dict | None:
    match = _TOKEN_RE.fullmatch(token or "")
    if not match:
        return None
    row = db.get_conn().execute(
        "SELECT sa.* FROM service_accounts sa JOIN accounts a ON a.id=sa.owner_id "
        "WHERE sa.id=? AND sa.revoked_at IS NULL AND a.suspended_at<=0",
        (match.group(1),),
    ).fetchone()
    if not row or not secrets.compare_digest(str(row["token_hash"]), _hash(token)):
        return None
    public = _public(row)
    if required_scope and required_scope not in public["scopes"]:
        return None
    return public


def consume_rate_limit(service_account_id: str, now: float | None = None) -> bool:
    current = time.time() if now is None else float(now)
    window = int(current // 60) * 60
    conn = db.get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO service_rate_windows(service_account_id,window_start,count) VALUES (?,?,0)",
        (service_account_id, window),
    )
    cur = conn.execute(
        "UPDATE service_rate_windows SET count=count+1 "
        "WHERE service_account_id=? AND window_start=? AND count<?",
        (service_account_id, window, settings.RELAY_RATE_LIMIT_PER_MINUTE),
    )
    conn.execute(
        "DELETE FROM service_rate_windows WHERE window_start<?", (window - 3600,),
    )
    conn.commit()
    return cur.rowcount > 0


def register_device(owner_id: str, device_id: str, name: str = "") -> dict:
    if not _DEVICE_RE.fullmatch(device_id):
        raise ValueError("invalid device id")
    now = time.time()
    db.get_conn().execute(
        "INSERT INTO relay_devices(owner_id,device_id,name,created_at,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(owner_id,device_id) DO UPDATE SET name=excluded.name,last_seen=excluded.last_seen",
        (owner_id, device_id, name[:80], now, now),
    )
    db.get_conn().commit()
    return {"owner_id": owner_id, "device_id": device_id, "name": name[:80], "last_seen": now}


def list_devices(owner_id: str) -> list[dict]:
    return [dict(row) for row in db.get_conn().execute(
        "SELECT device_id,name,created_at,last_seen FROM relay_devices WHERE owner_id=? ORDER BY last_seen DESC",
        (owner_id,),
    ).fetchall()]


def create_event(
    service: dict, *, event_key: str, device_id: str, automation_id: str,
    payload: dict[str, Any], payload_sha256: str,
) -> tuple[dict, bool, bool]:
    if not _EVENT_KEY_RE.fullmatch(event_key):
        raise ValueError("invalid event key")
    device = db.get_conn().execute(
        "SELECT 1 FROM relay_devices WHERE owner_id=? AND device_id=?",
        (service["owner_id"], device_id),
    ).fetchone()
    if not device:
        raise LookupError("relay device not registered")
    now = time.time()
    event_id = db.new_uuid()
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    try:
        db.get_conn().execute(
            "INSERT INTO relay_events "
            "(id,service_account_id,owner_id,device_id,automation_id,event_key,payload,payload_sha256,"
            "status,max_attempts,available_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,'pending',?,?,?,?)",
            (event_id, service["id"], service["owner_id"], device_id, automation_id,
             event_key, encoded, payload_sha256, settings.RELAY_MAX_ATTEMPTS, now, now, now),
        )
        db.get_conn().commit()
        return event_view(event_id), True, False
    except sqlite3.IntegrityError:
        db.get_conn().rollback()
        row = db.get_conn().execute(
            "SELECT * FROM relay_events WHERE service_account_id=? AND event_key=?",
            (service["id"], event_key),
        ).fetchone()
        if not row:
            raise
        conflict = (
            row["payload_sha256"] != payload_sha256 or row["device_id"] != device_id
            or row["automation_id"] != automation_id
        )
        return _event_public(row), False, conflict


def _event_public(row: sqlite3.Row, *, include_payload: bool = False) -> dict:
    item = {
        "id": row["id"], "service_account_id": row["service_account_id"],
        "owner_id": row["owner_id"], "device_id": row["device_id"],
        "automation_id": row["automation_id"], "event_key": row["event_key"],
        "status": row["status"], "attempt": row["attempt"],
        "max_attempts": row["max_attempts"], "available_at": row["available_at"],
        "lease_until": row["lease_until"], "error_code": row["error_code"],
        "error_message": row["error_message"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], "acknowledged_at": row["acknowledged_at"],
    }
    if include_payload:
        item["payload"] = json.loads(row["payload"] or "{}")
    return item


def event_view(event_id: str, service_account_id: str | None = None) -> dict | None:
    sql = "SELECT * FROM relay_events WHERE id=?"
    values: tuple[Any, ...] = (event_id,)
    if service_account_id:
        sql += " AND service_account_id=?"
        values += (service_account_id,)
    row = db.get_conn().execute(sql, values).fetchone()
    return _event_public(row) if row else None


def lease_events(owner_id: str, device_id: str, limit: int = 10) -> list[dict]:
    register_device(owner_id, device_id)
    now = time.time()
    conn = db.get_conn()
    conn.execute(
        "UPDATE relay_events SET status='pending',lease_token_hash=NULL,lease_until=NULL,"
        "available_at=?,updated_at=? WHERE owner_id=? AND device_id=? AND status='leased' "
        "AND lease_until<=? AND attempt<max_attempts",
        (now, now, owner_id, device_id, now),
    )
    conn.execute(
        "UPDATE relay_events SET status='dead_letter',error_code='lease_exhausted',updated_at=? "
        "WHERE owner_id=? AND device_id=? AND status='leased' AND lease_until<=? AND attempt>=max_attempts",
        (now, owner_id, device_id, now),
    )
    rows = conn.execute(
        "SELECT id FROM relay_events WHERE owner_id=? AND device_id=? AND status='pending' "
        "AND available_at<=? ORDER BY created_at LIMIT ?",
        (owner_id, device_id, now, max(1, min(limit, 25))),
    ).fetchall()
    leased: list[dict] = []
    for row in rows:
        lease_token = secrets.token_urlsafe(24)
        cur = conn.execute(
            "UPDATE relay_events SET status='leased',attempt=attempt+1,lease_token_hash=?,"
            "lease_until=?,updated_at=? WHERE id=? AND status='pending'",
            (_hash(lease_token), now + settings.RELAY_LEASE_SECONDS, now, row["id"]),
        )
        if cur.rowcount:
            current = conn.execute("SELECT * FROM relay_events WHERE id=?", (row["id"],)).fetchone()
            item = _event_public(current, include_payload=True)
            item["lease_token"] = lease_token
            leased.append(item)
    conn.commit()
    return leased


def acknowledge(
    event_id: str, owner_id: str, device_id: str, lease_token: str,
    *, status: str, error_code: str = "", error_message: str = "",
) -> dict | None:
    row = db.get_conn().execute(
        "SELECT * FROM relay_events WHERE id=? AND owner_id=? AND device_id=? "
        "AND status='leased' AND lease_until>?",
        (event_id, owner_id, device_id, time.time()),
    ).fetchone()
    if not row or not row["lease_token_hash"] or not secrets.compare_digest(
        row["lease_token_hash"], _hash(lease_token)
    ):
        return None
    now = time.time()
    target = "succeeded" if status == "succeeded" else "failed"
    db.get_conn().execute(
        "UPDATE relay_events SET status=?,lease_token_hash=NULL,lease_until=NULL,error_code=?,"
        "error_message=?,acknowledged_at=?,updated_at=? WHERE id=?",
        (target, error_code[:80] or None, error_message[:500] or None, now, now, event_id),
    )
    db.get_conn().commit()
    return event_view(event_id)


def cleanup_terminal_events(now: float | None = None) -> dict[str, Any]:
    """Bound terminal relay storage without touching pending or leased delivery."""
    current = time.time() if now is None else float(now)
    payload_cutoff = current - settings.RELAY_PAYLOAD_RETENTION_SECONDS
    row_cutoff = current - settings.RELAY_TERMINAL_RETENTION_SECONDS
    conn = db.get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        deleted = conn.execute(
            "DELETE FROM relay_events WHERE status IN ('succeeded','failed','dead_letter') "
            "AND COALESCE(acknowledged_at,updated_at,created_at)<=?",
            (row_cutoff,),
        ).rowcount
        tombstoned = conn.execute(
            "UPDATE relay_events SET payload='{}',payload_tombstoned_at=?,updated_at=? "
            "WHERE status IN ('succeeded','failed','dead_letter') "
            "AND COALESCE(acknowledged_at,updated_at,created_at)<=? "
            "AND payload_tombstoned_at IS NULL",
            (current, current, payload_cutoff),
        ).rowcount
        owners = [row[0] for row in conn.execute(
            "SELECT DISTINCT owner_id FROM relay_events "
            "WHERE status IN ('succeeded','failed','dead_letter')"
        ).fetchall()]
        cap = settings.RELAY_MAX_TERMINAL_ROWS_PER_OWNER
        for owner_id in owners:
            overflow = conn.execute(
                "SELECT id FROM relay_events WHERE owner_id=? "
                "AND status IN ('succeeded','failed','dead_letter') "
                "ORDER BY COALESCE(acknowledged_at,updated_at,created_at) DESC,id DESC "
                "LIMIT -1 OFFSET ?",
                (owner_id, cap),
            ).fetchall()
            if overflow:
                placeholders = ",".join("?" for _ in overflow)
                deleted += conn.execute(
                    f"DELETE FROM relay_events WHERE id IN ({placeholders})",
                    [row[0] for row in overflow],
                ).rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    result = {
        "last_run_at": current,
        "payloads_tombstoned": int(tombstoned),
        "rows_deleted": int(deleted),
    }
    _cleanup_state.update(result)
    return dict(result)


def retention_snapshot() -> dict[str, Any]:
    counts = {
        str(row["status"]): int(row["count"])
        for row in db.get_conn().execute(
            "SELECT status,COUNT(*) AS count FROM relay_events GROUP BY status"
        ).fetchall()
    }
    return {
        **_cleanup_state,
        "counts": counts,
        "payload_retention_seconds": settings.RELAY_PAYLOAD_RETENTION_SECONDS,
        "terminal_retention_seconds": settings.RELAY_TERMINAL_RETENTION_SECONDS,
        "max_terminal_rows_per_owner": settings.RELAY_MAX_TERMINAL_ROWS_PER_OWNER,
    }
