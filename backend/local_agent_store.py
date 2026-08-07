"""Minimal durable storage owned by Local Agent Core (WB-434/WB-436).

This database is intentionally not a business mirror. It contains only device
identity material, Server session bindings, active lease metadata and the
unacknowledged Run event WAL and device-local Asset working-copy state.
"""
from __future__ import annotations

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
        """
    )
    conn.commit()
    _local.initialized = True


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
    }


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
