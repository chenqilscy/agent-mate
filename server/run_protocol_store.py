"""Device identity and reliable, fenced Run transport (WB-433)."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import business_store
import db


PROTOCOL_VERSION = 1
CHALLENGE_TTL_SECONDS = 300
DEVICE_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_EVENT_BYTES = 256 * 1024
TERMINAL_STATUSES = {"completed", "succeeded", "failed", "cancelled"}


class ProtocolConflict(ValueError):
    pass


class ProtocolUnauthorized(ValueError):
    pass


class SequenceGap(ValueError):
    def __init__(self, expected_sequence: int) -> None:
        super().__init__(f"event sequence gap; expected {expected_sequence}")
        self.expected_sequence = expected_sequence


@dataclass(frozen=True)
class DevicePrincipal:
    device_id: str
    owner_id: str
    capabilities: dict[str, Any]
    protocol_version: int


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


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


def _token_hash(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _challenge_message(challenge_id: str, device_id: str, nonce: str) -> str:
    return f"agentmate-device-auth-v1:{challenge_id}:{device_id}:{nonce}"


def event_digest(
    *, run_id: str, device_id: str, lease_epoch: int, sequence: int,
    event_type: str, occurred_at: float, payload: dict[str, Any],
) -> str:
    envelope = {
        "device_id": device_id,
        "lease_epoch": lease_epoch,
        "occurred_at": occurred_at,
        "payload": payload,
        "run_id": run_id,
        "sequence": sequence,
        "type": event_type,
    }
    return hashlib.sha256(_json(envelope).encode("utf-8")).hexdigest()


def register_device(
    *, owner_id: str, device_id: str, name: str, public_key: str,
    protocol_version: int, app_version: str, platform: str, arch: str,
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    if protocol_version != PROTOCOL_VERSION:
        raise ProtocolConflict("unsupported device protocol version")
    try:
        raw_key = base64.b64decode(public_key, validate=True)
        Ed25519PublicKey.from_public_bytes(raw_key)
    except (ValueError, TypeError) as exc:
        raise ProtocolConflict("invalid Ed25519 public key") from exc
    if len(raw_key) != 32:
        raise ProtocolConflict("invalid Ed25519 public key")
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM agent_devices WHERE id=?", (device_id,)).fetchone()
        if existing is not None:
            if str(existing["owner_id"]) != owner_id:
                raise ProtocolConflict("device id already belongs to another account")
            if float(existing["revoked_at"]) > 0 or str(existing["status"]) == "revoked":
                raise ProtocolConflict("device is revoked; register a new device identity")
            if str(existing["public_key"]) != public_key:
                raise ProtocolConflict("device public key does not match registered identity")
            conn.execute(
                "UPDATE agent_devices SET name=?,protocol_version=?,app_version=?,platform=?,arch=?,"
                "capabilities=?,updated_at=? WHERE id=?",
                (name, protocol_version, app_version, platform, arch, _json(capabilities), now, device_id),
            )
        else:
            conn.execute(
                "INSERT INTO agent_devices "
                "(id,owner_id,name,public_key,protocol_version,app_version,platform,arch,capabilities,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'pending',?,?)",
                (device_id, owner_id, name, public_key, protocol_version, app_version, platform, arch,
                 _json(capabilities), now, now),
            )
        challenge_id = db.new_uuid()
        nonce = secrets.token_urlsafe(32)
        expires_at = now + CHALLENGE_TTL_SECONDS
        conn.execute(
            "INSERT INTO device_challenges (id,device_id,owner_id,nonce,expires_at,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (challenge_id, device_id, owner_id, nonce, expires_at, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "challenge_id": challenge_id,
        "challenge": _challenge_message(challenge_id, device_id, nonce),
        "expires_at": expires_at,
        "protocol_version": PROTOCOL_VERSION,
    }


def verify_device(*, owner_id: str, device_id: str, challenge_id: str, signature: str) -> dict[str, Any]:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT c.*,d.public_key,d.status,d.revoked_at FROM device_challenges c "
            "JOIN agent_devices d ON d.id=c.device_id WHERE c.id=? AND c.device_id=? AND c.owner_id=?",
            (challenge_id, device_id, owner_id),
        ).fetchone()
        if row is None or float(row["used_at"]) > 0 or float(row["expires_at"]) <= now:
            raise ProtocolUnauthorized("device challenge is invalid or expired")
        if str(row["status"]) == "revoked" or float(row["revoked_at"]) > 0:
            raise ProtocolUnauthorized("device is revoked")
        try:
            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(str(row["public_key"])))
            public_key.verify(
                base64.b64decode(signature, validate=True),
                _challenge_message(challenge_id, device_id, str(row["nonce"])).encode("utf-8"),
            )
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise ProtocolUnauthorized("device signature verification failed") from exc
        token = secrets.token_urlsafe(48)
        expires_at = now + DEVICE_TOKEN_TTL_SECONDS
        conn.execute("UPDATE device_challenges SET used_at=? WHERE id=?", (now, challenge_id))
        conn.execute(
            "UPDATE agent_devices SET status='active',authenticated_at=?,last_seen_at=?,updated_at=? WHERE id=?",
            (now, now, now, device_id),
        )
        conn.execute(
            "INSERT INTO device_tokens (token_hash,device_id,owner_id,expires_at,created_at,last_used_at) "
            "VALUES (?,?,?,?,?,?)",
            (_token_hash(token), device_id, owner_id, expires_at, now, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"device_token": token, "expires_at": expires_at, "protocol_version": PROTOCOL_VERSION}


def authenticate_device(authorization: str) -> DevicePrincipal:
    token = authorization[7:].strip() if authorization[:7].lower() == "device " else ""
    if not token:
        raise ProtocolUnauthorized("device authentication required")
    now = time.time()
    conn = db.get_conn()
    row = conn.execute(
        "SELECT t.*,d.capabilities,d.protocol_version,d.status,d.revoked_at AS device_revoked_at,"
        "a.suspended_at FROM device_tokens t JOIN agent_devices d ON d.id=t.device_id "
        "JOIN accounts a ON a.id=t.owner_id WHERE t.token_hash=?",
        (_token_hash(token),),
    ).fetchone()
    if (
        row is None or float(row["expires_at"]) <= now or float(row["revoked_at"]) > 0
        or float(row["device_revoked_at"]) > 0 or float(row["suspended_at"]) > 0
        or str(row["status"]) != "active"
    ):
        raise ProtocolUnauthorized("device token is invalid, expired or revoked")
    conn.execute("UPDATE device_tokens SET last_used_at=? WHERE token_hash=?", (now, row["token_hash"]))
    conn.execute("UPDATE agent_devices SET last_seen_at=?,updated_at=? WHERE id=?", (now, now, row["device_id"]))
    conn.commit()
    return DevicePrincipal(
        device_id=str(row["device_id"]), owner_id=str(row["owner_id"]),
        capabilities=_decode_json(row["capabilities"], {}),
        protocol_version=int(row["protocol_version"]),
    )


def heartbeat(principal: DevicePrincipal, capabilities: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    db.get_conn().execute(
        "UPDATE agent_devices SET capabilities=?,last_seen_at=?,updated_at=? WHERE id=? AND owner_id=?",
        (_json(capabilities), now, now, principal.device_id, principal.owner_id),
    )
    db.get_conn().commit()
    return {"server_time": now, "protocol_version": PROTOCOL_VERSION}


def list_devices(owner_id: str) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT id,name,protocol_version,app_version,platform,arch,capabilities,status,created_at,"
        "authenticated_at,last_seen_at,revoked_at FROM agent_devices WHERE owner_id=? ORDER BY created_at",
        (owner_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["capabilities"] = _decode_json(item["capabilities"], {})
        result.append(item)
    return result


def revoke_device(*, owner_id: str, device_id: str) -> bool:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM agent_devices WHERE id=? AND owner_id=?", (device_id, owner_id),
        ).fetchone()
        if row is None:
            conn.commit()
            return False
        conn.execute(
            "UPDATE agent_devices SET status='revoked',revoked_at=?,updated_at=? WHERE id=?",
            (now, now, device_id),
        )
        conn.execute("UPDATE device_tokens SET revoked_at=? WHERE device_id=? AND revoked_at=0", (now, device_id))
        leases = conn.execute(
            "SELECT id,run_id FROM run_leases WHERE device_id=? AND status='active'", (device_id,),
        ).fetchall()
        for lease in leases:
            conn.execute("UPDATE run_leases SET status='revoked' WHERE id=?", (lease["id"],))
            _recover_run(conn, str(lease["run_id"]), now)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def _recover_run(conn: sqlite3.Connection, run_id: str, now: float) -> None:
    run = conn.execute("SELECT * FROM business_runs WHERE id=?", (run_id,)).fetchone()
    if run is None or str(run["status"]) in TERMINAL_STATUSES:
        return
    recovery_count = int(run["recovery_count"]) + 1
    if recovery_count > int(run["max_recoveries"]):
        conn.execute(
            "UPDATE business_runs SET status='failed',recovery_count=?,error_code='lease_recovery_exhausted',"
            "error_message='Run lease recovery limit exceeded',ended_at=?,updated_at=?,version=version+1 WHERE id=?",
            (recovery_count, now, now, run_id),
        )
    else:
        conn.execute(
            "UPDATE business_runs SET status='recoverable',recovery_count=?,updated_at=?,version=version+1 WHERE id=?",
            (recovery_count, now, run_id),
        )


def _expire_leases(conn: sqlite3.Connection, now: float, owner_id: str | None = None) -> None:
    suffix = " AND owner_id=?" if owner_id else ""
    params: tuple[Any, ...] = (now, owner_id) if owner_id else (now,)
    rows = conn.execute(
        f"SELECT id,run_id FROM run_leases WHERE status='active' AND expires_at<=?{suffix}", params,
    ).fetchall()
    for row in rows:
        conn.execute("UPDATE run_leases SET status='expired' WHERE id=?", (row["id"],))
        _recover_run(conn, str(row["run_id"]), now)


def _capability_set(capabilities: dict[str, Any]) -> set[str]:
    declared = capabilities.get("capabilities", [])
    result = {str(item) for item in declared if isinstance(item, str)} if isinstance(declared, list) else set()
    tools = capabilities.get("supported_tools", {})
    if isinstance(tools, dict):
        result.update(f"tool:{name}" for name in tools)
    return result


def lease_run(principal: DevicePrincipal, *, lease_seconds: int) -> dict[str, Any] | None:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _expire_leases(conn, now, principal.owner_id)
        rows = conn.execute(
            "SELECT * FROM business_runs WHERE owner_id=? AND deleted_at=0 AND status IN ('queued','recoverable') "
            "ORDER BY created_at,id LIMIT 100",
            (principal.owner_id,),
        ).fetchall()
        available = _capability_set(principal.capabilities)
        selected = None
        for row in rows:
            target = str(row["target_device_id"] or "")
            required = set(_decode_json(row["required_capabilities"], []))
            if target and target != principal.device_id:
                continue
            if not required.issubset(available):
                continue
            selected = row
            break
        if selected is None:
            conn.commit()
            return None
        epoch = int(selected["lease_epoch"]) + 1
        lease_id = db.new_uuid()
        expires_at = now + max(5, min(300, lease_seconds))
        conn.execute(
            "UPDATE business_runs SET status='leased',lease_epoch=?,updated_at=?,version=version+1 WHERE id=?",
            (epoch, now, selected["id"]),
        )
        conn.execute(
            "INSERT INTO run_leases (id,run_id,owner_id,device_id,lease_epoch,issued_at,expires_at,renewed_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (lease_id, selected["id"], principal.owner_id, principal.device_id, epoch, now, expires_at, now),
        )
        row = conn.execute("SELECT * FROM business_runs WHERE id=?", (selected["id"],)).fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    run = business_store.decode_row(row) or {}
    return {
        "lease_id": lease_id, "lease_epoch": epoch, "expires_at": expires_at,
        "run": run, "ack_high_water": 0,
    }


def _current_lease(
    conn: sqlite3.Connection, principal: DevicePrincipal, run_id: str, lease_id: str, lease_epoch: int,
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT l.*,r.status AS run_status,r.lease_epoch AS current_epoch,r.cancel_version "
        "FROM run_leases l JOIN business_runs r ON r.id=l.run_id "
        "WHERE l.id=? AND l.run_id=? AND l.device_id=? AND l.owner_id=?",
        (lease_id, run_id, principal.device_id, principal.owner_id),
    ).fetchone()
    if row is None or int(row["lease_epoch"]) != lease_epoch or int(row["current_epoch"]) != lease_epoch:
        raise ProtocolConflict("stale or foreign Run lease")
    return row


def renew_lease(
    principal: DevicePrincipal, *, run_id: str, lease_id: str, lease_epoch: int, lease_seconds: int,
) -> dict[str, Any]:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = _current_lease(conn, principal, run_id, lease_id, lease_epoch)
        if str(row["status"]) != "active" or float(row["expires_at"]) <= now:
            if str(row["status"]) == "active":
                conn.execute("UPDATE run_leases SET status='expired' WHERE id=?", (lease_id,))
                _recover_run(conn, run_id, now)
            raise ProtocolConflict("Run lease expired or inactive")
        expires_at = now + max(5, min(300, lease_seconds))
        conn.execute(
            "UPDATE run_leases SET expires_at=?,renewed_at=? WHERE id=?",
            (expires_at, now, lease_id),
        )
        commands = _pending_commands(conn, run_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"expires_at": expires_at, "ack_high_water": int(row["ack_high_water"]), "commands": commands}


def _pending_commands(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id,command_type,version,payload,created_at FROM run_commands "
        "WHERE run_id=? AND status='pending' ORDER BY version,id", (run_id,),
    ).fetchall()
    return [
        {**dict(row), "payload": _decode_json(row["payload"], {})}
        for row in rows
    ]


def pending_commands(
    principal: DevicePrincipal, *, run_id: str, lease_id: str, lease_epoch: int,
) -> list[dict[str, Any]]:
    conn = db.get_conn()
    row = _current_lease(conn, principal, run_id, lease_id, lease_epoch)
    if str(row["status"]) not in {"active", "completed"}:
        raise ProtocolConflict("Run lease is inactive")
    return _pending_commands(conn, run_id)


def _apply_event(conn: sqlite3.Connection, row: sqlite3.Row, event: dict[str, Any], now: float) -> bool:
    event_type = str(event["type"])
    run_id = str(row["run_id"])
    payload = event["payload"]
    fields: dict[str, Any] = {"updated_at": now}
    terminal = False
    if event_type == "run.started":
        fields.update(status="running", started_at=event["occurred_at"])
    elif event_type == "run.waiting_user":
        fields.update(status="waiting_user")
    elif event_type == "run.checkpoint":
        fields.update(checkpoint=_json(payload))
    elif event_type == "run.completed":
        fields.update(status="completed", ended_at=event["occurred_at"], error_code="", error_message="")
        terminal = True
    elif event_type == "run.failed":
        fields.update(
            status="failed", ended_at=event["occurred_at"],
            error_code=str(payload.get("error_code") or "run_failed")[:200],
            error_message=str(payload.get("error_message") or "")[:20000],
        )
        terminal = True
    elif event_type in {"run.cancelled", "run.cancel_ack"}:
        fields.update(status="cancelled", ended_at=event["occurred_at"])
        terminal = True
        conn.execute(
            "UPDATE run_commands SET status='acknowledged',acknowledged_at=? "
            "WHERE run_id=? AND command_type='cancel' AND status='pending'",
            (now, run_id),
        )
    elif event_type == "command.ack":
        command_id = str(payload.get("command_id") or "")
        conn.execute(
            "UPDATE run_commands SET status='acknowledged',acknowledged_at=? WHERE id=? AND run_id=?",
            (now, command_id, run_id),
        )
    if fields:
        assignments = ",".join(f"{key}=?" for key in fields)
        conn.execute(
            f"UPDATE business_runs SET {assignments},version=version+1 WHERE id=?",
            (*fields.values(), run_id),
        )
    return terminal


def submit_events(
    principal: DevicePrincipal, *, run_id: str, lease_id: str, lease_epoch: int,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        lease = _current_lease(conn, principal, run_id, lease_id, lease_epoch)
        ack = int(lease["ack_high_water"])
        terminal_event_id = str(lease["terminal_event_id"] or "")
        for event in events:
            sequence = int(event["sequence"])
            payload = event["payload"]
            raw_payload = _json(payload).encode("utf-8")
            if len(raw_payload) > MAX_EVENT_BYTES:
                raise ProtocolConflict("Run event payload exceeds size limit")
            if _contains_secret_key(payload):
                raise ProtocolConflict("Run event payload must not contain credentials or secrets")
            expected_hash = event_digest(
                run_id=run_id, device_id=principal.device_id, lease_epoch=lease_epoch,
                sequence=sequence, event_type=str(event["type"]),
                occurred_at=float(event["occurred_at"]), payload=payload,
            )
            if not secrets.compare_digest(expected_hash, str(event["hash"])):
                raise ProtocolConflict("Run event hash mismatch")
            existing = conn.execute(
                "SELECT * FROM run_events WHERE event_id=? OR (run_id=? AND lease_epoch=? AND sequence=?)",
                (event["event_id"], run_id, lease_epoch, sequence),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["event_id"]) != str(event["event_id"])
                    or str(existing["payload_hash"]) != expected_hash
                    or str(existing["event_type"]) != str(event["type"])
                ):
                    raise ProtocolConflict("Run event id or sequence was reused with different content")
                if sequence > ack:
                    if sequence != ack + 1:
                        raise SequenceGap(ack + 1)
                    ack = sequence
                continue
            if str(lease["status"]) != "active" or float(lease["expires_at"]) <= now:
                if str(lease["status"]) == "active":
                    conn.execute("UPDATE run_leases SET status='expired' WHERE id=?", (lease_id,))
                    _recover_run(conn, run_id, now)
                raise ProtocolConflict("Run lease expired or inactive")
            if sequence != ack + 1:
                raise SequenceGap(ack + 1)
            conn.execute(
                "INSERT INTO run_events "
                "(event_id,run_id,lease_id,owner_id,device_id,lease_epoch,sequence,event_type,occurred_at,payload,payload_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (event["event_id"], run_id, lease_id, principal.owner_id, principal.device_id,
                 lease_epoch, sequence, event["type"], event["occurred_at"],
                 raw_payload.decode("utf-8"), expected_hash, now),
            )
            ack = sequence
            if _apply_event(conn, lease, event, now):
                terminal_event_id = str(event["event_id"])
                conn.execute(
                    "UPDATE run_leases SET status='completed',terminal_event_id=? WHERE id=?",
                    (terminal_event_id, lease_id),
                )
        conn.execute("UPDATE run_leases SET ack_high_water=? WHERE id=?", (ack, lease_id))
        commands = _pending_commands(conn, run_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"ack_high_water": ack, "terminal_event_id": terminal_event_id, "commands": commands}


def request_cancel(*, run_id: str, owner_id: str) -> dict[str, Any]:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM business_runs WHERE id=?", (run_id,)).fetchone()
        if run is None or str(run["owner_id"]) != owner_id:
            raise KeyError(run_id)
        if str(run["status"]) in TERMINAL_STATUSES:
            conn.commit()
            return business_store.decode_row(run) or {}
        version = int(run["cancel_version"]) + 1
        conn.execute(
            "UPDATE business_runs SET cancel_version=?,cancel_requested_at=?,updated_at=?,version=version+1 WHERE id=?",
            (version, now, now, run_id),
        )
        conn.execute(
            "INSERT INTO run_commands (id,run_id,owner_id,command_type,version,payload,created_at) "
            "VALUES (?,?,?,?,?,'{}',?)",
            (db.new_uuid(), run_id, owner_id, "cancel", version, now),
        )
        row = conn.execute("SELECT * FROM business_runs WHERE id=?", (run_id,)).fetchone()
        conn.commit()
        return business_store.decode_row(row) or {}
    except Exception:
        conn.rollback()
        raise


def answer_user(*, run_id: str, owner_id: str, question_event_id: str, answer: str) -> dict[str, Any]:
    now = time.time()
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        run = conn.execute("SELECT * FROM business_runs WHERE id=?", (run_id,)).fetchone()
        if run is None or str(run["owner_id"]) != owner_id:
            raise KeyError(run_id)
        question = conn.execute(
            "SELECT event_id FROM run_events WHERE event_id=? AND run_id=? AND event_type='run.waiting_user'",
            (question_event_id, run_id),
        ).fetchone()
        if question is None or str(run["status"]) != "waiting_user":
            raise ProtocolConflict("Run is not waiting for that question")
        version = int(conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM run_commands WHERE run_id=?", (run_id,),
        ).fetchone()[0])
        command_id = db.new_uuid()
        conn.execute(
            "INSERT INTO run_commands (id,run_id,owner_id,command_type,version,payload,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (command_id, run_id, owner_id, "ask_user_answer", version,
             _json({"question_event_id": question_event_id, "answer": answer}), now),
        )
        conn.commit()
        return {"id": command_id, "version": version, "status": "pending"}
    except Exception:
        conn.rollback()
        raise
