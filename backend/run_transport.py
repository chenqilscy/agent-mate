"""Local Agent device identity and durable Server Run event transport (WB-433).

The scheduler only registers/heartbeats and flushes existing WAL rows here.
Actual Run claiming/execution is deliberately left to the Local Agent Core
cut-over so this protocol cannot consume work before an executor owns it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import server_client
import server_sync
from config import settings
from storage import db


PROTOCOL_VERSION = 1
MAX_EVENT_BYTES = 256 * 1024


class WalCapacityExceeded(RuntimeError):
    """Execution must pause; dropping a Run event is forbidden."""


class LeaseFenced(RuntimeError):
    """The Server rejected this lease epoch; the old worker must stop."""


_SECRET_KEYS = {
    "token", "secret", "password", "apikey", "authorization", "credential",
    "privatekey", "accesstoken", "refreshtoken", "clientsecret",
}


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in _SECRET_KEYS or _contains_secret_key(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _owner_key(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:24]


def _setting(owner_id: str, suffix: str) -> str:
    return f"server.run_device.{_owner_key(owner_id)}.{suffix}"


def device_id(owner_id: str) -> str:
    key = _setting(owner_id, "id")
    value = db.get_device_setting(key)
    if value:
        return value
    value = f"device-{uuid.uuid4()}"
    db.set_device_setting(key, value)
    return value


def _private_key(owner_id: str) -> Ed25519PrivateKey:
    key = _setting(owner_id, "private_key")
    encoded = db.get_device_secret(key)
    if encoded:
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded))
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    db.set_device_secret(key, base64.b64encode(raw).decode("ascii"))
    return private


def _public_capabilities() -> dict[str, Any]:
    report = dict(server_sync._capability_report(""))
    report.pop("revision", None)
    report["capabilities"] = ["run_events_v1", "local_workspace", "ask_user"]
    return report


def ensure_device(owner_id: str, user_token: str) -> str | None:
    token_key = _setting(owner_id, "token")
    expiry_key = _setting(owner_id, "token_expires_at")
    token = db.get_device_secret(token_key)
    expires_at = float(db.get_device_setting(expiry_key) or 0)
    if token and expires_at > time.time() + 60:
        return token

    private = _private_key(owner_id)
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    capabilities = _public_capabilities()
    registered = server_client.register_run_device(user_token, {
        "device_id": device_id(owner_id),
        "name": "AgentMate Local Agent",
        "public_key": base64.b64encode(public).decode("ascii"),
        "protocol_version": PROTOCOL_VERSION,
        "app_version": settings.APP_VERSION,
        "platform": str(capabilities.get("platform") or ""),
        "arch": str(capabilities.get("arch") or ""),
        "capabilities": capabilities,
    })
    challenge = registered.get("challenge") if isinstance(registered, dict) else None
    if not isinstance(challenge, dict):
        return None
    challenge_id = str(challenge.get("challenge_id") or "")
    message = str(challenge.get("challenge") or "")
    if not challenge_id or not message:
        return None
    signature = base64.b64encode(private.sign(message.encode("utf-8"))).decode("ascii")
    verified = server_client.verify_run_device(
        user_token, device_id(owner_id), challenge_id, signature,
    )
    token = str(verified.get("device_token") or "") if isinstance(verified, dict) else ""
    if not token:
        return None
    db.set_device_secret(token_key, token)
    db.set_device_setting(expiry_key, str(float(verified.get("expires_at") or 0)))
    return token


def clear_device_token(owner_id: str) -> None:
    db.set_device_secret(_setting(owner_id, "token"), None)
    db.set_device_setting(_setting(owner_id, "token_expires_at"), None)


def heartbeat(owner_id: str, device_token: str) -> bool:
    status, _payload = server_client.device_post(
        "/api/agent/heartbeat", device_token, {"capabilities": _public_capabilities()},
    )
    if status == 401:
        clear_device_token(owner_id)
    return status == 200


def record_lease(owner_id: str, lease: dict[str, Any]) -> dict[str, Any]:
    run = lease.get("run") if isinstance(lease.get("run"), dict) else {}
    run_id = str(run.get("id") or "")
    lease_id = str(lease.get("lease_id") or "")
    epoch = int(lease.get("lease_epoch") or 0)
    if not run_id or not lease_id or epoch < 1:
        raise ValueError("invalid Run lease")
    now = time.time()
    db.get_conn().execute(
        "INSERT INTO run_transport_leases "
        "(run_id,owner_id,device_id,lease_id,lease_epoch,expires_at,ack_high_water,status,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET "
        "owner_id=excluded.owner_id,device_id=excluded.device_id,lease_id=excluded.lease_id,"
        "lease_epoch=excluded.lease_epoch,expires_at=excluded.expires_at,"
        "ack_high_water=excluded.ack_high_water,status='active',last_error='',updated_at=excluded.updated_at",
        (run_id, owner_id, device_id(owner_id), lease_id, epoch,
         float(lease.get("expires_at") or 0), int(lease.get("ack_high_water") or 0), "active", now),
    )
    db.get_conn().commit()
    return run


def claim_run(owner_id: str, device_token: str, *, lease_seconds: int = 30) -> dict[str, Any] | None:
    status, response = server_client.device_post(
        "/api/agent/runs/lease", device_token, {"lease_seconds": lease_seconds},
    )
    if status == 401:
        clear_device_token(owner_id)
        return None
    lease = response.get("lease") if status == 200 and isinstance(response, dict) else None
    if not isinstance(lease, dict):
        return None
    return record_lease(owner_id, lease)


def _event_digest(
    *, run_id: str, device: str, lease_epoch: int, sequence: int,
    event_type: str, occurred_at: float, payload: dict[str, Any],
) -> str:
    envelope = {
        "device_id": device, "lease_epoch": lease_epoch, "occurred_at": occurred_at,
        "payload": payload, "run_id": run_id, "sequence": sequence, "type": event_type,
    }
    return hashlib.sha256(_json(envelope).encode("utf-8")).hexdigest()


def append_event(
    run_id: str, event_type: str, payload: dict[str, Any] | None = None,
    *, occurred_at: float | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    raw_payload = _json(payload)
    if len(raw_payload.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ValueError("Run event payload exceeds size limit")
    if _contains_secret_key(payload):
        raise ValueError("Run event payload must not contain credentials or secrets")
    conn = db.get_conn()
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        lease = conn.execute("SELECT * FROM run_transport_leases WHERE run_id=?", (run_id,)).fetchone()
        if lease is None or str(lease["status"]) != "active":
            raise LeaseFenced("Run has no active local lease")
        total_bytes = int(conn.execute("SELECT COALESCE(SUM(byte_size),0) FROM run_event_wal").fetchone()[0])
        sequence = int(conn.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM run_event_wal WHERE run_id=? AND lease_epoch=?",
            (run_id, lease["lease_epoch"]),
        ).fetchone()[0])
        # WAL rows already ACKed are deleted, so retain the Server high-water when
        # allocating after a restart with an empty local queue.
        sequence = max(sequence, int(lease["ack_high_water"]) + 1)
        occurred = float(occurred_at or now)
        event_id = str(uuid.uuid4())
        digest = _event_digest(
            run_id=run_id, device=str(lease["device_id"]), lease_epoch=int(lease["lease_epoch"]),
            sequence=sequence, event_type=event_type, occurred_at=occurred, payload=payload,
        )
        byte_size = len(raw_payload.encode("utf-8")) + len(event_type.encode("utf-8")) + 256
        if total_bytes + byte_size > settings.RUN_EVENT_WAL_MAX_BYTES:
            raise WalCapacityExceeded("Run event WAL is full; execution must pause until Server ACK")
        conn.execute(
            "INSERT INTO run_event_wal "
            "(event_id,run_id,owner_id,device_id,lease_id,lease_epoch,sequence,event_type,occurred_at,payload,payload_hash,byte_size,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, run_id, lease["owner_id"], lease["device_id"], lease["lease_id"],
             lease["lease_epoch"], sequence, event_type, occurred, raw_payload, digest, byte_size, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "event_id": event_id, "sequence": sequence, "type": event_type,
        "occurred_at": occurred, "payload": payload, "hash": digest,
    }


def _mark_transport_error(run_id: str, status: str, message: str) -> None:
    db.get_conn().execute(
        "UPDATE run_transport_leases SET status=?,last_error=?,updated_at=? WHERE run_id=?",
        (status, message[:500], time.time(), run_id),
    )
    db.get_conn().commit()


def flush_wal(owner_id: str, device_token: str, *, batch_size: int = 100) -> dict[str, int]:
    leases = db.get_conn().execute(
        "SELECT * FROM run_transport_leases WHERE owner_id=? AND status='active' ORDER BY updated_at",
        (owner_id,),
    ).fetchall()
    acknowledged = 0
    pending = 0
    for lease in leases:
        rows = db.get_conn().execute(
            "SELECT * FROM run_event_wal WHERE run_id=? AND lease_epoch=? ORDER BY sequence LIMIT ?",
            (lease["run_id"], lease["lease_epoch"], max(1, min(100, batch_size))),
        ).fetchall()
        if not rows:
            continue
        pending += len(rows)
        events = [{
            "event_id": row["event_id"], "sequence": row["sequence"], "type": row["event_type"],
            "occurred_at": row["occurred_at"], "payload": json.loads(row["payload"]),
            "hash": row["payload_hash"],
        } for row in rows]
        now = time.time()
        db.get_conn().execute(
            "UPDATE run_event_wal SET attempts=attempts+1,last_attempt_at=? "
            "WHERE run_id=? AND lease_epoch=? AND sequence BETWEEN ? AND ?",
            (now, lease["run_id"], lease["lease_epoch"], rows[0]["sequence"], rows[-1]["sequence"]),
        )
        db.get_conn().commit()
        status, response = server_client.device_post(
            f"/api/agent/runs/{lease['run_id']}/leases/{lease['lease_id']}/events",
            device_token, {"lease_epoch": lease["lease_epoch"], "events": events},
        )
        if status == 401:
            clear_device_token(owner_id)
            break
        if status == 409:
            detail = response.get("detail") if isinstance(response, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else ""
            if code == "event_sequence_gap":
                expected = int(detail.get("expected_sequence") or 0)
                have = {int(row["sequence"]) for row in rows}
                if expected not in have:
                    _mark_transport_error(str(lease["run_id"]), "fenced", f"WAL missing sequence {expected}")
            else:
                _mark_transport_error(str(lease["run_id"]), "fenced", str(detail or "lease rejected"))
            continue
        if status != 200 or not isinstance(response, dict):
            continue
        ack = int(response.get("ack_high_water") or 0)
        if ack < int(lease["ack_high_water"]):
            _mark_transport_error(str(lease["run_id"]), "fenced", "Server ACK moved backwards")
            continue
        conn = db.get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            deleted = conn.execute(
                "DELETE FROM run_event_wal WHERE run_id=? AND lease_epoch=? AND sequence<=?",
                (lease["run_id"], lease["lease_epoch"], ack),
            ).rowcount
            conn.execute(
                "UPDATE run_transport_leases SET ack_high_water=?,last_error='',updated_at=? WHERE run_id=?",
                (ack, time.time(), lease["run_id"]),
            )
            conn.commit()
            acknowledged += max(0, deleted)
        except Exception:
            conn.rollback()
            raise
    remaining = int(db.get_conn().execute(
        "SELECT COUNT(*) FROM run_event_wal WHERE owner_id=?", (owner_id,),
    ).fetchone()[0])
    return {"acknowledged": acknowledged, "pending": remaining}


def renew_lease(run_id: str, device_token: str, *, lease_seconds: int = 30) -> dict[str, Any]:
    lease = db.get_conn().execute("SELECT * FROM run_transport_leases WHERE run_id=?", (run_id,)).fetchone()
    if lease is None or str(lease["status"]) != "active":
        raise LeaseFenced("Run has no active local lease")
    status, response = server_client.device_post(
        f"/api/agent/runs/{run_id}/leases/{lease['lease_id']}/renew", device_token,
        {"lease_epoch": lease["lease_epoch"], "lease_seconds": lease_seconds},
    )
    if status != 200 or not isinstance(response, dict):
        if status in {401, 409}:
            _mark_transport_error(run_id, "fenced", "lease renewal rejected")
            raise LeaseFenced("Run lease renewal rejected")
        return {}
    db.get_conn().execute(
        "UPDATE run_transport_leases SET expires_at=?,ack_high_water=?,updated_at=? WHERE run_id=?",
        (float(response.get("expires_at") or 0), int(response.get("ack_high_water") or 0), time.time(), run_id),
    )
    db.get_conn().commit()
    return response


def maintain_transport() -> dict[str, int]:
    """Register/heartbeat each signed-in owner and flush durable events; never claim work."""
    online = 0
    acknowledged = 0
    pending = 0
    for owner_id, user_token in db.list_server_identities():
        token = ensure_device(owner_id, user_token)
        if not token:
            continue
        if heartbeat(owner_id, token):
            online += 1
        result = flush_wal(owner_id, token)
        acknowledged += result["acknowledged"]
        pending += result["pending"]
    return {"online": online, "acknowledged": acknowledged, "pending": pending}
