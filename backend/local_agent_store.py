"""Minimal durable storage owned by Local Agent Core (WB-434/WB-436).

This database is intentionally not a business mirror. It contains only device
identity material, Server session bindings, active lease metadata and the
unacknowledged Run event WAL and device-local Asset working-copy state.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

import local_secret_store
from config import settings


_local = threading.local()


def _connect() -> sqlite3.Connection:
    path = Path(settings.LOCAL_AGENT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    current_path = str(Path(settings.LOCAL_AGENT_DB_PATH).resolve())
    if conn is None or getattr(_local, "path", "") != current_path:
        if conn is not None:
            conn.close()
        conn = _connect()
        _local.conn = conn
        _local.path = current_path
        _local.initialized = False
    return conn


def close_thread_connection() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None
    _local.path = ""
    _local.initialized = False


def retire_superseded_wal(
    conn: sqlite3.Connection,
    run_id: str,
    current_epoch: int,
    *,
    retired_at: float | None = None,
) -> int:
    """Move fenced older-epoch events out of the retry queue without losing audit data.

    The caller owns the transaction. A Server-issued higher epoch makes older
    envelopes permanently ineligible for upload, but they are retained locally
    instead of being silently deleted as if they had received an ACK.
    """
    retired = float(retired_at or time.time())
    conn.execute(
        "INSERT OR IGNORE INTO retired_run_event_wal "
        "(event_id,run_id,owner_id,device_id,lease_id,lease_epoch,sequence,event_type,"
        "occurred_at,payload,payload_hash,byte_size,attempts,last_attempt_at,created_at,"
        "retired_reason,superseded_by_epoch,retired_at) "
        "SELECT event_id,run_id,owner_id,device_id,lease_id,lease_epoch,sequence,event_type,"
        "occurred_at,payload,payload_hash,byte_size,attempts,last_attempt_at,created_at,"
        "'lease_epoch_superseded',?,? FROM run_event_wal "
        "WHERE run_id=? AND lease_epoch<?",
        (current_epoch, retired, run_id, current_epoch),
    )
    return conn.execute(
        "DELETE FROM run_event_wal WHERE run_id=? AND lease_epoch<? "
        "AND event_id IN (SELECT event_id FROM retired_run_event_wal)",
        (run_id, current_epoch),
    ).rowcount


def init_db() -> None:
    if getattr(_local, "initialized", False):
        return
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS local_agent_schema (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL
        );
        INSERT OR IGNORE INTO local_agent_schema(version,applied_at)
            VALUES (1,CAST(strftime('%s','now') AS REAL));

        CREATE TABLE IF NOT EXISTS device_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS device_secrets (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS server_identities (
            owner_id TEXT PRIMARY KEY,
            server_token TEXT NOT NULL,
            expires_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_transport_leases (
            run_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lease_id TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            expires_at REAL NOT NULL,
            ack_high_water INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            last_error TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_transport_leases_owner
            ON run_transport_leases(owner_id,status,updated_at);

        CREATE TABLE IF NOT EXISTS run_event_wal (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lease_id TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at REAL NOT NULL,
            payload TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt_at REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            UNIQUE(run_id,lease_epoch,sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_run_event_wal_flush
            ON run_event_wal(owner_id,run_id,lease_epoch,sequence);

        CREATE TABLE IF NOT EXISTS retired_run_event_wal (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lease_id TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at REAL NOT NULL,
            payload TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt_at REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            retired_reason TEXT NOT NULL,
            superseded_by_epoch INTEGER NOT NULL,
            retired_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_retired_run_event_wal_owner
            ON retired_run_event_wal(owner_id,run_id,lease_epoch);

        CREATE TABLE IF NOT EXISTS run_input_staging (
            request_key TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_input_staging_owner
            ON run_input_staging(owner_id,created_at);

        CREATE TABLE IF NOT EXISTS asset_working_copies (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            asset_id TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            relative_path TEXT NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'workspace',
            state TEXT NOT NULL DEFAULT 'local-only',
            size INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL DEFAULT '',
            upload_id TEXT NOT NULL DEFAULT '',
            object_version_id TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner_id,source_kind,relative_path)
        );
        CREATE INDEX IF NOT EXISTS idx_asset_working_copies_owner_state
            ON asset_working_copies(owner_id,state,updated_at DESC);
        CREATE TABLE IF NOT EXISTS asset_working_copy_audit (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            working_copy_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            FOREIGN KEY(working_copy_id) REFERENCES asset_working_copies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS connector_instances (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            transport TEXT NOT NULL,
            command TEXT NOT NULL DEFAULT '',
            args TEXT NOT NULL DEFAULT '[]',
            url TEXT NOT NULL DEFAULT '',
            environment TEXT NOT NULL DEFAULT '{}',
            secret_keys TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            health_status TEXT NOT NULL DEFAULT 'unknown',
            last_error TEXT NOT NULL DEFAULT '',
            tool_count INTEGER NOT NULL DEFAULT 0,
            last_checked_at REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner_id,name)
        );
        CREATE INDEX IF NOT EXISTS idx_connector_instances_owner
            ON connector_instances(owner_id,enabled,name);
        CREATE TABLE IF NOT EXISTS run_worker_leader (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            holder_id TEXT NOT NULL,
            expires_at REAL NOT NULL,
            snapshot TEXT NOT NULL DEFAULT '{}',
            updated_at REAL NOT NULL
        );
        INSERT OR IGNORE INTO local_agent_schema(version,applied_at)
            VALUES (2,CAST(strftime('%s','now') AS REAL));
        INSERT OR IGNORE INTO local_agent_schema(version,applied_at)
            VALUES (3,CAST(strftime('%s','now') AS REAL));
        INSERT OR IGNORE INTO local_agent_schema(version,applied_at)
            VALUES (4,CAST(strftime('%s','now') AS REAL));
        """
    )
    try:
        conn.execute("BEGIN IMMEDIATE")
        for lease in conn.execute(
            "SELECT run_id,lease_epoch FROM run_transport_leases WHERE lease_epoch>0"
        ).fetchall():
            retire_superseded_wal(conn, str(lease["run_id"]), int(lease["lease_epoch"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    _local.initialized = True


def acquire_run_worker_leader(holder_id: str, *, ttl_seconds: float = 15.0) -> bool:
    """Acquire or renew the single claimant for this Local Agent database."""
    init_db()
    conn = get_conn()
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT holder_id,expires_at FROM run_worker_leader WHERE singleton=1",
        ).fetchone()
        if row is not None and str(row["holder_id"]) != holder_id and float(row["expires_at"]) > now:
            conn.commit()
            return False
        snapshot = "{}" if row is None or str(row["holder_id"]) != holder_id else None
        if row is None:
            conn.execute(
                "INSERT INTO run_worker_leader(singleton,holder_id,expires_at,snapshot,updated_at) "
                "VALUES (1,?,?,?,?)",
                (holder_id, now + max(5.0, ttl_seconds), "{}", now),
            )
        elif snapshot is None:
            conn.execute(
                "UPDATE run_worker_leader SET expires_at=?,updated_at=? WHERE singleton=1 AND holder_id=?",
                (now + max(5.0, ttl_seconds), now, holder_id),
            )
        else:
            conn.execute(
                "UPDATE run_worker_leader SET holder_id=?,expires_at=?,snapshot='{}',updated_at=? "
                "WHERE singleton=1",
                (holder_id, now + max(5.0, ttl_seconds), now),
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def publish_run_worker_snapshot(holder_id: str, snapshot: dict) -> bool:
    init_db()
    now = time.time()
    updated = get_conn().execute(
        "UPDATE run_worker_leader SET snapshot=?,updated_at=? "
        "WHERE singleton=1 AND holder_id=? AND expires_at>?",
        (json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), now, holder_id, now),
    ).rowcount
    get_conn().commit()
    return bool(updated)


def read_run_worker_snapshot() -> dict:
    init_db()
    row = get_conn().execute(
        "SELECT holder_id,expires_at,snapshot,updated_at FROM run_worker_leader WHERE singleton=1",
    ).fetchone()
    if row is None or float(row["expires_at"] or 0) <= time.time():
        return {"leader_active": False, "holder_id": "", "snapshot": {}, "updated_at": 0}
    try:
        snapshot = json.loads(str(row["snapshot"] or "{}"))
    except json.JSONDecodeError:
        snapshot = {}
    return {
        "leader_active": True, "holder_id": str(row["holder_id"]),
        "snapshot": snapshot if isinstance(snapshot, dict) else {},
        "updated_at": float(row["updated_at"] or 0),
    }


def release_run_worker_leader(holder_id: str) -> None:
    init_db()
    get_conn().execute(
        "UPDATE run_worker_leader SET expires_at=0,snapshot='{}',updated_at=? "
        "WHERE singleton=1 AND holder_id=?",
        (time.time(), holder_id),
    )
    get_conn().commit()


def get_device_setting(key: str) -> Optional[str]:
    init_db()
    row = get_conn().execute("SELECT value FROM device_settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else None


def set_device_setting(key: str, value: Optional[str]) -> None:
    init_db()
    if value is None:
        get_conn().execute("DELETE FROM device_settings WHERE key=?", (key,))
    else:
        get_conn().execute(
            "INSERT INTO device_settings(key,value,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (key, value, time.time()),
        )
    get_conn().commit()


def get_device_secret(key: str) -> Optional[str]:
    init_db()
    row = get_conn().execute("SELECT value FROM device_secrets WHERE key=?", (key,)).fetchone()
    return local_secret_store.unprotect(str(row["value"])) if row else None


def set_device_secret(key: str, value: Optional[str]) -> None:
    init_db()
    if not value:
        get_conn().execute("DELETE FROM device_secrets WHERE key=?", (key,))
    else:
        get_conn().execute(
            "INSERT INTO device_secrets(key,value,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (key, local_secret_store.protect(value), time.time()),
        )
    get_conn().commit()


def _connector_secret_key(owner_id: str, connector_id: str, name: str) -> str:
    return f"connector:{owner_id}:{connector_id}:{name}"


def set_connector_secret(owner_id: str, connector_id: str, name: str, value: Optional[str]) -> None:
    set_device_secret(_connector_secret_key(owner_id, connector_id, name), value)


def get_connector_secret(owner_id: str, connector_id: str, name: str) -> Optional[str]:
    return get_device_secret(_connector_secret_key(owner_id, connector_id, name))


def set_builtin_connector_secret(owner_id: str, connector_name: str, name: str, value: Optional[str]) -> None:
    set_connector_secret(owner_id, f"builtin:{connector_name}", name, value)


def get_builtin_connector_secret(owner_id: str, connector_name: str, name: str) -> Optional[str]:
    return get_connector_secret(owner_id, f"builtin:{connector_name}", name)


def _connector_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    for key, fallback in (("args", []), ("environment", {}), ("secret_keys", [])):
        try:
            item[key] = json.loads(str(item[key]))
        except (TypeError, json.JSONDecodeError):
            item[key] = fallback
    item["enabled"] = bool(item["enabled"])
    item["has_secrets"] = {
        key: bool(get_connector_secret(str(item["owner_id"]), str(item["id"]), key))
        for key in item["secret_keys"]
    }
    return item


def list_connector_instances(owner_id: str, *, enabled_only: bool = False) -> list[dict]:
    init_db()
    suffix = " AND enabled=1" if enabled_only else ""
    rows = get_conn().execute(
        f"SELECT * FROM connector_instances WHERE owner_id=?{suffix} ORDER BY name,id",
        (owner_id,),
    ).fetchall()
    return [_connector_row(row) for row in rows]


def get_connector_instance(owner_id: str, instance_id: str) -> Optional[dict]:
    init_db()
    row = get_conn().execute(
        "SELECT * FROM connector_instances WHERE id=? AND owner_id=?", (instance_id, owner_id),
    ).fetchone()
    return _connector_row(row) if row else None


def save_connector_instance(
    owner_id: str, *, instance_id: str, name: str, transport: str,
    command: str = "", args: list[str] | None = None, url: str = "",
    environment: dict[str, str] | None = None, secret_keys: list[str] | None = None,
    enabled: bool = True,
) -> dict:
    init_db()
    now = time.time()
    existing = get_connector_instance(owner_id, instance_id)
    conn = get_conn()
    conn.execute(
        "INSERT INTO connector_instances "
        "(id,owner_id,name,transport,command,args,url,environment,secret_keys,enabled,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "name=excluded.name,transport=excluded.transport,command=excluded.command,args=excluded.args,"
        "url=excluded.url,environment=excluded.environment,secret_keys=excluded.secret_keys,"
        "enabled=excluded.enabled,health_status='unknown',last_error='',tool_count=0,updated_at=excluded.updated_at "
        "WHERE connector_instances.owner_id=excluded.owner_id",
        (
            instance_id, owner_id, name, transport, command,
            json.dumps(args or [], ensure_ascii=False), url,
            json.dumps(environment or {}, ensure_ascii=False),
            json.dumps(secret_keys or [], ensure_ascii=False), int(enabled),
            float(existing["created_at"]) if existing else now, now,
        ),
    )
    conn.commit()
    result = get_connector_instance(owner_id, instance_id)
    if result is None:
        raise KeyError(instance_id)
    return result


def set_connector_health(
    owner_id: str, instance_id: str, *, status: str, error: str = "", tool_count: int = 0,
) -> Optional[dict]:
    init_db()
    get_conn().execute(
        "UPDATE connector_instances SET health_status=?,last_error=?,tool_count=?,last_checked_at=?,updated_at=? "
        "WHERE id=? AND owner_id=?",
        (status, error[:2000], max(0, tool_count), time.time(), time.time(), instance_id, owner_id),
    )
    get_conn().commit()
    return get_connector_instance(owner_id, instance_id)


def delete_connector_instance(owner_id: str, instance_id: str) -> bool:
    instance = get_connector_instance(owner_id, instance_id)
    if instance is None:
        return False
    for key in instance["secret_keys"]:
        set_connector_secret(owner_id, instance_id, key, None)
    cur = get_conn().execute(
        "DELETE FROM connector_instances WHERE id=? AND owner_id=?", (instance_id, owner_id),
    )
    get_conn().commit()
    return cur.rowcount > 0


def set_server_identity(owner_id: str, token: str, expires_at: float | None = None) -> None:
    init_db()
    expiry = float(expires_at or (time.time() + settings.SERVER_TOKEN_OFFLINE_GRACE_SECONDS))
    get_conn().execute(
        "INSERT INTO server_identities(owner_id,server_token,expires_at,updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(owner_id) DO UPDATE SET server_token=excluded.server_token,"
        "expires_at=excluded.expires_at,updated_at=excluded.updated_at",
        (owner_id, local_secret_store.protect(token), expiry, time.time()),
    )
    get_conn().commit()


def get_server_identity(owner_id: str) -> Optional[str]:
    init_db()
    row = get_conn().execute(
        "SELECT server_token FROM server_identities WHERE owner_id=? AND expires_at>?",
        (owner_id, time.time()),
    ).fetchone()
    return local_secret_store.unprotect(str(row["server_token"])) if row else None


def list_server_identities() -> list[tuple[str, str]]:
    init_db()
    rows = get_conn().execute(
        "SELECT owner_id,server_token FROM server_identities WHERE expires_at>? ORDER BY owner_id",
        (time.time(),),
    ).fetchall()
    return [
        (str(row["owner_id"]), local_secret_store.unprotect(str(row["server_token"])))
        for row in rows
    ]


def clear_server_identity_by_token(token: str) -> None:
    init_db()
    rows = get_conn().execute("SELECT owner_id,server_token FROM server_identities").fetchall()
    owner_ids = [
        str(row["owner_id"]) for row in rows
        if secrets.compare_digest(local_secret_store.unprotect(str(row["server_token"])), token)
    ]
    get_conn().executemany("DELETE FROM server_identities WHERE owner_id=?", [(item,) for item in owner_ids])
    get_conn().commit()


def clear_server_identity(owner_id: str) -> None:
    init_db()
    get_conn().execute("DELETE FROM server_identities WHERE owner_id=?", (owner_id,))
    get_conn().commit()


def stage_run_input(owner_id: str, request_key: str, payload: dict) -> None:
    init_db()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    size = len(raw.encode("utf-8"))
    if size > 8 * 1024 * 1024:
        raise ValueError("local Run input exceeds 8 MiB")
    now = time.time()
    conn = get_conn()
    conn.execute("DELETE FROM run_input_staging WHERE created_at<?", (now - 24 * 60 * 60,))
    conn.execute(
        "INSERT INTO run_input_staging(request_key,owner_id,payload,byte_size,created_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(request_key) DO UPDATE SET owner_id=excluded.owner_id,payload=excluded.payload,"
        "byte_size=excluded.byte_size,created_at=excluded.created_at",
        (request_key, owner_id, raw, size, now),
    )
    conn.commit()


def take_run_input(owner_id: str, request_key: str) -> dict | None:
    """Read staged input without consuming it.

    A claimed Run can be recovered after a process crash.  Keeping the input
    until the normal 24-hour cleanup window makes that recovery deterministic;
    the opaque key remains owner-scoped and the payload never leaves this
    Local Agent database.
    """
    init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT payload FROM run_input_staging WHERE request_key=? AND owner_id=?",
        (request_key, owner_id),
    ).fetchone()
    if row is None:
        return None
    value = json.loads(str(row["payload"]))
    return value if isinstance(value, dict) else None


def clear_run_input(owner_id: str, request_key: str) -> bool:
    """Delete terminal Run input only after the Server ACK closed its lease."""
    if not request_key:
        return False
    init_db()
    deleted = get_conn().execute(
        "DELETE FROM run_input_staging WHERE request_key=? AND owner_id=?",
        (request_key, owner_id),
    ).rowcount
    get_conn().commit()
    return bool(deleted)


def status_snapshot() -> dict:
    init_db()
    conn = get_conn()
    wal = conn.execute(
        "SELECT COUNT(*) AS count,COALESCE(SUM(byte_size),0) AS bytes,MIN(created_at) AS oldest "
        "FROM run_event_wal"
    ).fetchone()
    leases = conn.execute(
        "SELECT COUNT(*) AS count,SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active "
        "FROM run_transport_leases"
    ).fetchone()
    errors = conn.execute(
        "SELECT run_id,last_error FROM run_transport_leases WHERE last_error<>'' "
        "ORDER BY updated_at DESC LIMIT 10"
    ).fetchall()
    identities = int(conn.execute(
        "SELECT COUNT(*) FROM server_identities WHERE expires_at>?", (time.time(),),
    ).fetchone()[0])
    working_copies = {
        str(row["state"]): int(row["count"])
        for row in conn.execute(
            "SELECT state,COUNT(*) AS count FROM asset_working_copies GROUP BY state"
        ).fetchall()
    }
    return {
        "identities": identities,
        "leases": {"total": int(leases["count"] or 0), "active": int(leases["active"] or 0)},
        "wal": {
            "count": int(wal["count"] or 0), "bytes": int(wal["bytes"] or 0),
            "oldest_at": float(wal["oldest"] or 0),
        },
        "errors": [{"run_id": str(row["run_id"]), "error": str(row["last_error"])} for row in errors],
        "working_copies": working_copies,
        "staged_inputs": int(conn.execute("SELECT COUNT(*) FROM run_input_staging").fetchone()[0]),
    }


def diagnostics_snapshot(owner_id: str) -> dict:
    """Owner-scoped transport details; never includes tokens, paths or secret values."""
    init_db()
    conn = get_conn()
    now = time.time()
    identity = conn.execute(
        "SELECT expires_at,updated_at FROM server_identities WHERE owner_id=?", (owner_id,),
    ).fetchone()
    leases = [dict(row) for row in conn.execute(
        "SELECT run_id,device_id,lease_epoch,expires_at,ack_high_water,status,last_error,updated_at "
        "FROM run_transport_leases WHERE owner_id=? ORDER BY updated_at DESC LIMIT 50",
        (owner_id,),
    ).fetchall()]
    wal = conn.execute(
        "SELECT COUNT(*) AS count,COALESCE(SUM(byte_size),0) AS bytes,MIN(created_at) AS oldest,"
        "COALESCE(MAX(attempts),0) AS max_attempts FROM run_event_wal WHERE owner_id=?",
        (owner_id,),
    ).fetchone()
    wal_runs = [dict(row) for row in conn.execute(
        "SELECT run_id,lease_epoch,COUNT(*) AS count,COALESCE(SUM(byte_size),0) AS bytes,"
        "MIN(created_at) AS oldest_at,MAX(attempts) AS attempts "
        "FROM run_event_wal WHERE owner_id=? GROUP BY run_id,lease_epoch ORDER BY oldest_at LIMIT 50",
        (owner_id,),
    ).fetchall()]
    copies = [dict(row) for row in conn.execute(
        "SELECT id,asset_id,project_id,run_id,relative_path,source_kind,state,size,updated_at "
        "FROM asset_working_copies WHERE owner_id=? ORDER BY updated_at DESC LIMIT 50",
        (owner_id,),
    ).fetchall()]
    return {
        "identity": {
            "bound": bool(identity and float(identity["expires_at"]) > now),
            "expires_at": float(identity["expires_at"] or 0) if identity else 0,
            "updated_at": float(identity["updated_at"] or 0) if identity else 0,
        },
        "leases": leases,
        "wal": {
            "count": int(wal["count"] or 0), "bytes": int(wal["bytes"] or 0),
            "oldest_at": float(wal["oldest"] or 0), "max_attempts": int(wal["max_attempts"] or 0),
            "runs": wal_runs,
        },
        "working_copies": copies,
        "staged_inputs": int(conn.execute(
            "SELECT COUNT(*) FROM run_input_staging WHERE owner_id=?", (owner_id,),
        ).fetchone()[0]),
    }


def clear_completed_transport(owner_id: str) -> int:
    """Remove only fully ACKed terminal lease metadata; never touch WAL or active state."""
    init_db()
    deleted = get_conn().execute(
        "DELETE FROM run_transport_leases WHERE owner_id=? AND status='completed' "
        "AND NOT EXISTS (SELECT 1 FROM run_event_wal w WHERE w.run_id=run_transport_leases.run_id)",
        (owner_id,),
    ).rowcount
    get_conn().commit()
    return int(deleted)


def upsert_working_copy(
    *, owner_id: str, relative_path: str, source_kind: str, project_id: str = "",
    run_id: str = "", asset_id: str = "", state: str = "local-only", size: int = 0,
    sha256: str = "", upload_id: str = "", object_version_id: str = "",
) -> dict:
    """Persist only local path/state; the path is never sent to Server."""
    init_db()
    if state not in {"local-only", "uploading", "committed"}:
        raise ValueError("invalid working-copy state")
    if source_kind not in {"workspace", "external"}:
        raise ValueError("invalid working-copy source")
    conn = get_conn()
    now = time.time()
    row = conn.execute(
        "SELECT id FROM asset_working_copies WHERE owner_id=? AND source_kind=? AND relative_path=?",
        (owner_id, source_kind, relative_path),
    ).fetchone()
    copy_id = str(row["id"]) if row else secrets.token_hex(16)
    conn.execute(
        "INSERT INTO asset_working_copies "
        "(id,owner_id,asset_id,project_id,run_id,relative_path,source_kind,state,size,sha256,"
        "upload_id,object_version_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(owner_id,source_kind,relative_path) DO UPDATE SET "
        "asset_id=excluded.asset_id,project_id=excluded.project_id,run_id=excluded.run_id,"
        "state=excluded.state,size=excluded.size,sha256=excluded.sha256,upload_id=excluded.upload_id,"
        "object_version_id=excluded.object_version_id,updated_at=excluded.updated_at",
        (
            copy_id, owner_id, asset_id, project_id, run_id, relative_path, source_kind, state,
            size, sha256, upload_id, object_version_id, now, now,
        ),
    )
    conn.execute(
        "INSERT INTO asset_working_copy_audit(id,owner_id,working_copy_id,action,details,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (secrets.token_hex(16), owner_id, copy_id, f"state.{state}", "{}", now),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM asset_working_copies WHERE id=?", (copy_id,)).fetchone())


def get_working_copy(copy_id: str, owner_id: str) -> Optional[dict]:
    init_db()
    row = get_conn().execute(
        "SELECT * FROM asset_working_copies WHERE id=? AND owner_id=?", (copy_id, owner_id),
    ).fetchone()
    return dict(row) if row else None


def list_working_copies(owner_id: str) -> list[dict]:
    init_db()
    rows = get_conn().execute(
        "SELECT * FROM asset_working_copies WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_working_copy(copy_id: str, owner_id: str, *, action: str) -> bool:
    init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM asset_working_copies WHERE id=? AND owner_id=?", (copy_id, owner_id),
    ).fetchone()
    if not row:
        return False
    now = time.time()
    conn.execute(
        "INSERT INTO asset_working_copy_audit(id,owner_id,working_copy_id,action,details,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (secrets.token_hex(16), owner_id, copy_id, action, "{}", now),
    )
    # Keep the audit trail and tombstone the local state instead of cascading it.
    conn.execute(
        "UPDATE asset_working_copies SET state='local-only',asset_id='',upload_id='',"
        "object_version_id='',updated_at=? WHERE id=?", (now, copy_id),
    )
    conn.commit()
    return True
