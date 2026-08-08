"""Server-owned signed webhook configuration and idempotent delivery ledger."""
from __future__ import annotations

import secrets
import sqlite3
import time
from typing import Any

import db
import secret_crypto


def _context(webhook_id: str) -> str:
    return f"automation-webhook:{webhook_id}"


def _view(row: sqlite3.Row | None, *, include_secret: bool = False) -> dict[str, Any] | None:
    if row is None:
        return None
    result = {
        "id": str(row["id"]), "automation_id": str(row["automation_id"]),
        "owner_id": str(row["owner_id"]), "created_at": float(row["created_at"]),
        "rotated_at": float(row["rotated_at"]),
    }
    if include_secret:
        result["secret"] = secret_crypto.decrypt(
            str(row["secret_ciphertext"]), context=_context(str(row["id"])),
        )
    return result


def get(automation_id: str, owner_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
    row = db.get_conn().execute(
        "SELECT * FROM business_automation_webhooks WHERE automation_id=? AND owner_id=?",
        (automation_id, owner_id),
    ).fetchone()
    return _view(row, include_secret=include_secret)


def get_by_id(webhook_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
    row = db.get_conn().execute(
        "SELECT * FROM business_automation_webhooks WHERE id=?", (webhook_id,),
    ).fetchone()
    return _view(row, include_secret=include_secret)


def create(automation_id: str, owner_id: str) -> dict[str, Any]:
    webhook_id = "wh_" + secrets.token_urlsafe(18)
    secret = "whsec_" + secrets.token_urlsafe(32)
    now = time.time()
    db.get_conn().execute(
        "INSERT INTO business_automation_webhooks "
        "(id,automation_id,owner_id,secret_ciphertext,created_at,rotated_at) VALUES (?,?,?,?,?,0)",
        (
            webhook_id, automation_id, owner_id,
            secret_crypto.encrypt(secret, context=_context(webhook_id)), now,
        ),
    )
    db.get_conn().commit()
    return {**(get(automation_id, owner_id) or {}), "secret": secret}


def rotate(automation_id: str, owner_id: str) -> dict[str, Any] | None:
    current = get(automation_id, owner_id)
    if current is None:
        return None
    secret = "whsec_" + secrets.token_urlsafe(32)
    now = time.time()
    db.get_conn().execute(
        "UPDATE business_automation_webhooks SET secret_ciphertext=?,rotated_at=? "
        "WHERE automation_id=? AND owner_id=?",
        (
            secret_crypto.encrypt(secret, context=_context(str(current["id"]))),
            now, automation_id, owner_id,
        ),
    )
    db.get_conn().commit()
    return {**(get(automation_id, owner_id) or {}), "secret": secret}


def delete(automation_id: str, owner_id: str) -> bool:
    result = db.get_conn().execute(
        "DELETE FROM business_automation_webhooks WHERE automation_id=? AND owner_id=?",
        (automation_id, owner_id),
    )
    db.get_conn().commit()
    return result.rowcount == 1


def register_delivery(
    *, webhook_id: str, automation_id: str, owner_id: str,
    idempotency_key: str, payload_sha256: str,
) -> tuple[dict[str, Any], bool, bool]:
    conn = db.get_conn()
    now = time.time()
    try:
        conn.execute(
            "INSERT INTO business_automation_webhook_deliveries "
            "(id,webhook_id,automation_id,owner_id,idempotency_key,payload_sha256,status,received_at,updated_at) "
            "VALUES (?,?,?,?,?,?,'received',?,?)",
            (
                db.new_uuid(), webhook_id, automation_id, owner_id,
                idempotency_key, payload_sha256, now, now,
            ),
        )
        conn.commit()
        created = True
    except sqlite3.IntegrityError:
        conn.rollback()
        created = False
    row = conn.execute(
        "SELECT * FROM business_automation_webhook_deliveries "
        "WHERE webhook_id=? AND idempotency_key=?",
        (webhook_id, idempotency_key),
    ).fetchone()
    if row is None:
        raise RuntimeError("webhook delivery registration failed")
    result = dict(row)
    return result, created, str(row["payload_sha256"]) != payload_sha256


def update_delivery(
    delivery_id: str, *, status: str, fire_id: str | None = None, error_code: str = "",
) -> dict[str, Any]:
    conn = db.get_conn()
    conn.execute(
        "UPDATE business_automation_webhook_deliveries SET status=?,fire_id=COALESCE(?,fire_id),"
        "error_code=?,updated_at=? WHERE id=?",
        (status, fire_id, error_code, time.time(), delivery_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM business_automation_webhook_deliveries WHERE id=?", (delivery_id,),
    ).fetchone()
    if row is None:
        raise KeyError(delivery_id)
    return dict(row)


def list_deliveries(automation_id: str, owner_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT d.*,f.status AS fire_status FROM business_automation_webhook_deliveries d "
        "LEFT JOIN business_automation_fires f ON f.id=d.fire_id "
        "WHERE d.automation_id=? AND d.owner_id=? ORDER BY d.received_at DESC LIMIT ?",
        (automation_id, owner_id, max(1, min(100, limit))),
    ).fetchall()
    return [dict(row) for row in rows]
