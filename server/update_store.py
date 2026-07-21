"""Immutable desktop release registry and deterministic rollout selection (WB-257)."""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any

import db

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DEVICE_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
CHANNELS = {"stable", "beta"}
EVENTS = {"check", "offered", "no_update", "download_failed", "install_failed", "installed"}


def ensure_tables() -> None:
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS desktop_releases (
            id TEXT PRIMARY KEY,
            version TEXT NOT NULL UNIQUE,
            channel TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at REAL NOT NULL,
            published_at REAL
        );
        CREATE TABLE IF NOT EXISTS desktop_release_artifacts (
            release_id TEXT NOT NULL,
            target TEXT NOT NULL,
            arch TEXT NOT NULL,
            url TEXT NOT NULL,
            signature TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (release_id, target, arch),
            FOREIGN KEY (release_id) REFERENCES desktop_releases(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS desktop_update_channels (
            channel TEXT PRIMARY KEY,
            active_release_id TEXT,
            rollout_percent INTEGER NOT NULL DEFAULT 100,
            rollout_salt TEXT NOT NULL DEFAULT '',
            min_supported_version TEXT NOT NULL DEFAULT '0.0.0',
            paused INTEGER NOT NULL DEFAULT 0,
            rollback INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS desktop_update_events (
            id TEXT PRIMARY KEY,
            device_hash TEXT NOT NULL,
            channel TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '',
            arch TEXT NOT NULL DEFAULT '',
            current_version TEXT NOT NULL DEFAULT '',
            release_id TEXT,
            event TEXT NOT NULL,
            error_code TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_desktop_update_events_created
            ON desktop_update_events(created_at DESC);
        """
    )
    now = time.time()
    for channel in sorted(CHANNELS):
        conn.execute(
            "INSERT OR IGNORE INTO desktop_update_channels "
            "(channel, rollout_salt, updated_at) VALUES (?,?,?)",
            (channel, uuid.uuid4().hex, now),
        )
    conn.commit()


def version_tuple(value: str) -> tuple[int, int, int, tuple[str, ...]]:
    if not _VERSION_RE.fullmatch(value):
        raise ValueError("version must be semantic x.y.z")
    main, _, suffix = value.partition("-")
    suffix = suffix.split("+", 1)[0]
    major, minor, patch = (int(part) for part in main.split("."))
    # A final release sorts after a prerelease with the same numeric version.
    prerelease = ("~",) if not suffix else tuple(suffix.split("."))
    return major, minor, patch, prerelease


def validate_device_id(value: str) -> str:
    value = value.strip()
    if not _DEVICE_RE.fullmatch(value):
        raise ValueError("invalid device id")
    return value


def _device_hash(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()


def _bucket(device_id: str, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}:{device_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


def _decode_release(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    release = dict(row)
    release["artifacts"] = [
        dict(item) for item in db.get_conn().execute(
            "SELECT target,arch,url,signature,sha256,size_bytes "
            "FROM desktop_release_artifacts WHERE release_id=? ORDER BY target,arch",
            (release["id"],),
        ).fetchall()
    ]
    return release


def create_release(
    *, version: str, channel: str, notes: str, artifacts: list[dict[str, Any]], created_by: str,
) -> dict[str, Any]:
    version_tuple(version)
    if channel not in CHANNELS:
        raise ValueError("invalid channel")
    if not artifacts:
        raise ValueError("at least one signed artifact is required")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in artifacts:
        target = str(item.get("target", "")).strip()
        arch = str(item.get("arch", "")).strip()
        url = str(item.get("url", "")).strip()
        signature = str(item.get("signature", "")).strip()
        sha256 = str(item.get("sha256", "")).strip().lower()
        size_bytes = int(item.get("size_bytes", 0))
        if not target or not arch or (target, arch) in seen:
            raise ValueError("artifact target/arch must be unique")
        if not url.startswith("https://"):
            raise ValueError("artifact URL must use https")
        if len(signature) < 32:
            raise ValueError("artifact signature is missing or too short")
        if not _SHA256_RE.fullmatch(sha256) or size_bytes < 1:
            raise ValueError("artifact sha256/size is invalid")
        seen.add((target, arch))
        normalized.append({
            "target": target, "arch": arch, "url": url, "signature": signature,
            "sha256": sha256, "size_bytes": size_bytes,
        })
    conn = db.get_conn()
    release_id = str(uuid.uuid4())
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO desktop_releases (id,version,channel,notes,state,created_by,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (release_id, version, channel, notes.strip(), "draft", created_by, now),
        )
        for item in normalized:
            conn.execute(
                "INSERT INTO desktop_release_artifacts "
                "(release_id,target,arch,url,signature,sha256,size_bytes) VALUES (?,?,?,?,?,?,?)",
                (release_id, item["target"], item["arch"], item["url"], item["signature"],
                 item["sha256"], item["size_bytes"]),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_release(release_id) or {}


def get_release(release_id: str) -> dict[str, Any] | None:
    return _decode_release(db.get_conn().execute(
        "SELECT * FROM desktop_releases WHERE id=?", (release_id,),
    ).fetchone())


def list_releases() -> list[dict[str, Any]]:
    return [
        _decode_release(row) or {} for row in db.get_conn().execute(
            "SELECT * FROM desktop_releases ORDER BY created_at DESC"
        ).fetchall()
    ]


def publish_release(
    release_id: str, *, rollout_percent: int, min_supported_version: str,
) -> dict[str, Any]:
    release = get_release(release_id)
    if release is None:
        raise LookupError("release not found")
    if not 1 <= rollout_percent <= 100:
        raise ValueError("rollout_percent must be 1..100")
    version_tuple(min_supported_version)
    conn = db.get_conn()
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE desktop_releases SET state='published',published_at=COALESCE(published_at,?) WHERE id=?",
            (now, release_id),
        )
        conn.execute(
            "UPDATE desktop_update_channels SET active_release_id=?,rollout_percent=?,"
            "min_supported_version=?,paused=0,rollback=0,updated_at=? WHERE channel=?",
            (release_id, rollout_percent, min_supported_version, now, release["channel"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return channel_state(release["channel"])


def pause_channel(channel: str, paused: bool) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError("invalid channel")
    db.get_conn().execute(
        "UPDATE desktop_update_channels SET paused=?,updated_at=? WHERE channel=?",
        (int(paused), time.time(), channel),
    )
    db.get_conn().commit()
    return channel_state(channel)


def rollback_channel(channel: str, release_id: str) -> dict[str, Any]:
    release = get_release(release_id)
    if release is None or release["channel"] != channel:
        raise LookupError("release not found in channel")
    conn = db.get_conn()
    now = time.time()
    conn.execute(
        "UPDATE desktop_update_channels SET active_release_id=?,rollout_percent=100,paused=0,"
        "rollback=1,updated_at=? WHERE channel=?",
        (release_id, now, channel),
    )
    conn.execute("UPDATE desktop_releases SET state='published' WHERE id=?", (release_id,))
    conn.commit()
    return channel_state(channel)


def channel_state(channel: str) -> dict[str, Any]:
    row = db.get_conn().execute(
        "SELECT * FROM desktop_update_channels WHERE channel=?", (channel,),
    ).fetchone()
    if row is None:
        raise LookupError("channel not found")
    value = dict(row)
    value["paused"] = bool(value["paused"])
    value["rollback"] = bool(value["rollback"])
    return value


def record_event(
    *, device_id: str, channel: str, event: str, target: str = "", arch: str = "",
    current_version: str = "", release_id: str | None = None, error_code: str = "",
) -> None:
    validate_device_id(device_id)
    if channel not in CHANNELS or event not in EVENTS:
        raise ValueError("invalid update event")
    db.get_conn().execute(
        "INSERT INTO desktop_update_events "
        "(id,device_hash,channel,target,arch,current_version,release_id,event,error_code,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), _device_hash(device_id), channel, target[:40], arch[:40],
         current_version[:40], release_id, event, error_code[:120], time.time()),
    )
    db.get_conn().commit()


def select_update(
    *, channel: str, target: str, arch: str, current_version: str, device_id: str,
) -> dict[str, Any] | None:
    current = version_tuple(current_version)
    validate_device_id(device_id)
    state = channel_state(channel)
    if state["paused"] or not state["active_release_id"]:
        record_event(device_id=device_id, channel=channel, event="no_update", target=target,
                     arch=arch, current_version=current_version)
        return None
    release = get_release(state["active_release_id"])
    if release is None or release["state"] != "published":
        return None
    artifact = next(
        (item for item in release["artifacts"] if item["target"] == target and item["arch"] == arch), None,
    )
    if artifact is None:
        record_event(device_id=device_id, channel=channel, event="no_update", target=target,
                     arch=arch, current_version=current_version, release_id=release["id"])
        return None
    forced = current < version_tuple(state["min_supported_version"])
    eligible = forced or _bucket(device_id, state["rollout_salt"]) < state["rollout_percent"]
    is_new_version = version_tuple(release["version"]) > current
    is_rollback = state["rollback"] and version_tuple(release["version"]) != current
    if not eligible or not (is_new_version or is_rollback):
        record_event(device_id=device_id, channel=channel, event="no_update", target=target,
                     arch=arch, current_version=current_version, release_id=release["id"])
        return None
    record_event(device_id=device_id, channel=channel, event="offered", target=target,
                 arch=arch, current_version=current_version, release_id=release["id"])
    return {
        "version": release["version"],
        "notes": release["notes"],
        "pub_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(release["published_at"] or release["created_at"])),
        "url": artifact["url"],
        "signature": artifact["signature"],
        "rollback": bool(state["rollback"]),
        "forced": forced,
        "sha256": artifact["sha256"],
        "size_bytes": artifact["size_bytes"],
        "release_id": release["id"],
    }


def update_metrics() -> dict[str, Any]:
    rows = db.get_conn().execute(
        "SELECT event,COUNT(*) AS count FROM desktop_update_events GROUP BY event"
    ).fetchall()
    return {"events": {row["event"]: row["count"] for row in rows}, "channels": [channel_state(c) for c in sorted(CHANNELS)]}

