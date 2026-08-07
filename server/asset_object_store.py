"""Filesystem-backed immutable Asset objects and resumable upload state (WB-436)."""
from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

import business_store
import db
from config import settings


class ObjectConflict(ValueError):
    pass


def _root() -> Path:
    root = Path(settings.OBJECT_STORAGE_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _upload_dir(upload_id: str) -> Path:
    return _root() / "uploads" / upload_id


def _object_key(sha256: str) -> str:
    return f"objects/{sha256[:2]}/{sha256}"


def object_path(storage_key: str) -> Path:
    root = _root()
    path = (root / storage_key).resolve()
    if path == root or root not in path.parents:
        raise ObjectConflict("invalid object storage key")
    return path


def _audit(conn, asset: dict[str, Any], action: str, details: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO business_audit "
        "(id,actor_id,owner_id,project_id,action,entity_type,entity_id,details,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            db.new_uuid(), asset["owner_id"], asset["owner_id"], asset.get("project_id"),
            action, "asset", asset["id"], business_store._json(details), time.time(),
        ),
    )


def _version_row(conn, version_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM asset_object_versions WHERE id=? AND deleted_at=0", (version_id,),
    ).fetchone()
    return dict(row) if row else None


def _commit_version(conn, asset: dict[str, Any], *, storage_key: str, size: int, sha256: str) -> dict[str, Any]:
    number = int(conn.execute(
        "SELECT COALESCE(MAX(version_number),0)+1 FROM asset_object_versions WHERE asset_id=?",
        (asset["id"],),
    ).fetchone()[0])
    version_id = db.new_uuid()
    now = time.time()
    conn.execute(
        "INSERT INTO asset_object_versions "
        "(id,asset_id,owner_id,version_number,storage_key,size,sha256,retained_until,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            version_id, asset["id"], asset["owner_id"], number, storage_key, size, sha256,
            now + settings.ASSET_RETENTION_SECONDS, now,
        ),
    )
    object_ref = f"object://sha256/{sha256}?version={version_id}"
    conn.execute(
        "UPDATE business_assets SET size=?,sha256=?,storage_state='committed',object_ref=?,"
        "validation_status='verified',validation=?,version=version+1,updated_at=? "
        "WHERE id=? AND deleted_at=0",
        (
            size, sha256, object_ref,
            business_store._json({"sha256": sha256, "size": size, "verified_at": now}),
            now, asset["id"],
        ),
    )
    _audit(conn, asset, "asset.object.commit", {"object_version_id": version_id, "sha256": sha256, "size": size})
    return dict(conn.execute("SELECT * FROM asset_object_versions WHERE id=?", (version_id,)).fetchone())


def begin_upload(asset: dict[str, Any], *, expected_size: int, expected_sha256: str) -> dict[str, Any]:
    expected_sha256 = expected_sha256.lower()
    if expected_size < 0 or len(expected_sha256) != 64:
        raise ValueError("invalid object size or sha256")
    if asset.get("size") not in {0, expected_size}:
        raise ObjectConflict("asset size does not match upload")
    if asset.get("sha256") and str(asset["sha256"]).lower() != expected_sha256:
        raise ObjectConflict("asset sha256 does not match upload")
    conn = db.get_conn()
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute(
            "SELECT * FROM asset_uploads WHERE asset_id=? AND owner_id=? AND state='uploading' "
            "AND expected_size=? AND expected_sha256=? AND expires_at>? ORDER BY created_at DESC LIMIT 1",
            (asset["id"], asset["owner_id"], expected_size, expected_sha256, now),
        ).fetchone()
        if active:
            conn.commit()
            return {**dict(active), "deduplicated": False, "resumed": True}

        duplicate = conn.execute(
            "SELECT * FROM asset_object_versions WHERE owner_id=? AND sha256=? AND size=? "
            "AND deleted_at=0 ORDER BY created_at DESC LIMIT 1",
            (asset["owner_id"], expected_sha256, expected_size),
        ).fetchone()
        if duplicate and object_path(str(duplicate["storage_key"])).is_file():
            version = _commit_version(
                conn, asset, storage_key=str(duplicate["storage_key"]),
                size=expected_size, sha256=expected_sha256,
            )
            upload_id = db.new_uuid()
            conn.execute(
                "INSERT INTO asset_uploads "
                "(id,asset_id,owner_id,project_id,expected_size,expected_sha256,part_size,state,"
                "object_version_id,created_at,updated_at,expires_at,completed_at) "
                "VALUES (?,?,?,?,?,?,?,'committed',?,?,?,?,?)",
                (
                    upload_id, asset["id"], asset["owner_id"], asset.get("project_id"),
                    expected_size, expected_sha256, settings.ASSET_UPLOAD_PART_BYTES,
                    version["id"], now, now, now, now,
                ),
            )
            conn.commit()
            return {
                "id": upload_id, "asset_id": asset["id"], "state": "committed",
                "object_version_id": version["id"], "part_size": settings.ASSET_UPLOAD_PART_BYTES,
                "deduplicated": True, "resumed": False,
            }

        upload_id = db.new_uuid()
        conn.execute(
            "INSERT INTO asset_uploads "
            "(id,asset_id,owner_id,project_id,expected_size,expected_sha256,part_size,state,"
            "created_at,updated_at,expires_at) VALUES (?,?,?,?,?,?,?,'uploading',?,?,?)",
            (
                upload_id, asset["id"], asset["owner_id"], asset.get("project_id"),
                expected_size, expected_sha256, settings.ASSET_UPLOAD_PART_BYTES,
                now, now, now + settings.ASSET_UPLOAD_TTL_SECONDS,
            ),
        )
        _audit(conn, asset, "asset.upload.begin", {"upload_id": upload_id, "size": expected_size})
        conn.commit()
        _upload_dir(upload_id).mkdir(parents=True, exist_ok=True)
        return {
            "id": upload_id, "asset_id": asset["id"], "state": "uploading",
            "part_size": settings.ASSET_UPLOAD_PART_BYTES, "expires_at": now + settings.ASSET_UPLOAD_TTL_SECONDS,
            "deduplicated": False, "resumed": False,
        }
    except Exception:
        conn.rollback()
        raise


def upload_status(upload_id: str, owner_id: str) -> dict[str, Any]:
    row = db.get_conn().execute(
        "SELECT * FROM asset_uploads WHERE id=? AND owner_id=?", (upload_id, owner_id),
    ).fetchone()
    if not row:
        raise KeyError(upload_id)
    parts = db.get_conn().execute(
        "SELECT part_number,size,sha256 FROM asset_upload_parts WHERE upload_id=? ORDER BY part_number",
        (upload_id,),
    ).fetchall()
    return {**dict(row), "parts": [dict(part) for part in parts]}


def put_part(upload_id: str, owner_id: str, part_number: int, data: bytes, declared_sha256: str) -> dict[str, Any]:
    upload = upload_status(upload_id, owner_id)
    if upload["state"] != "uploading" or float(upload["expires_at"]) <= time.time():
        raise ObjectConflict("upload is not active")
    expected_size = int(upload["expected_size"])
    part_size = int(upload["part_size"])
    total_parts = max(1, (expected_size + part_size - 1) // part_size)
    if part_number < 0 or part_number >= total_parts:
        raise ValueError("part number is out of range")
    required = part_size if part_number < total_parts - 1 else expected_size - part_size * part_number
    if len(data) != required:
        raise ObjectConflict(f"part size mismatch: expected {required}")
    actual = hashlib.sha256(data).hexdigest()
    if declared_sha256.lower() != actual:
        raise ObjectConflict("part sha256 mismatch")
    conn = db.get_conn()
    existing = conn.execute(
        "SELECT size,sha256 FROM asset_upload_parts WHERE upload_id=? AND part_number=?",
        (upload_id, part_number),
    ).fetchone()
    if existing and (int(existing["size"]) != len(data) or str(existing["sha256"]) != actual):
        raise ObjectConflict("part was already uploaded with different content")
    directory = _upload_dir(upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{part_number:08d}.part"
    temporary = directory / f"{part_number:08d}.{secrets.token_hex(4)}.tmp"
    temporary.write_bytes(data)
    os.replace(temporary, target)
    now = time.time()
    conn.execute(
        "INSERT INTO asset_upload_parts(upload_id,part_number,size,sha256,created_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(upload_id,part_number) DO UPDATE SET size=excluded.size,sha256=excluded.sha256",
        (upload_id, part_number, len(data), actual, now),
    )
    conn.execute(
        "UPDATE asset_uploads SET updated_at=?,expires_at=? WHERE id=?",
        (now, now + settings.ASSET_UPLOAD_TTL_SECONDS, upload_id),
    )
    conn.commit()
    return {"part_number": part_number, "size": len(data), "sha256": actual}


def complete_upload(upload_id: str, owner_id: str) -> dict[str, Any]:
    upload = upload_status(upload_id, owner_id)
    if upload["state"] == "committed" and upload.get("object_version_id"):
        version = _version_row(db.get_conn(), str(upload["object_version_id"]))
        return {"upload": upload, "object_version": version, "duplicate": True}
    if upload["state"] != "uploading" or float(upload["expires_at"]) <= time.time():
        raise ObjectConflict("upload is not active")
    expected_size = int(upload["expected_size"])
    part_size = int(upload["part_size"])
    total_parts = 0 if expected_size == 0 else (expected_size + part_size - 1) // part_size
    parts = upload["parts"]
    if [int(item["part_number"]) for item in parts] != list(range(total_parts)):
        raise ObjectConflict("upload has missing parts")
    directory = _upload_dir(upload_id)
    assembled = directory / "assembled.tmp"
    digest = hashlib.sha256()
    size = 0
    with assembled.open("wb") as output:
        for number in range(total_parts):
            part_path = directory / f"{number:08d}.part"
            with part_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    actual = digest.hexdigest()
    if size != expected_size or actual != str(upload["expected_sha256"]):
        assembled.unlink(missing_ok=True)
        raise ObjectConflict("assembled object size or sha256 mismatch")
    storage_key = _object_key(actual)
    target = object_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size != size:
            assembled.unlink(missing_ok=True)
            raise ObjectConflict("content-addressed object has an invalid size")
        assembled.unlink(missing_ok=True)
    else:
        os.replace(assembled, target)
    conn = db.get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM asset_uploads WHERE id=?", (upload_id,)).fetchone()
        if not current or current["state"] != "uploading":
            raise ObjectConflict("upload was finalized concurrently")
        asset_row = conn.execute(
            "SELECT * FROM business_assets WHERE id=? AND deleted_at=0", (upload["asset_id"],),
        ).fetchone()
        if not asset_row:
            raise KeyError(str(upload["asset_id"]))
        asset = dict(asset_row)
        version = _commit_version(conn, asset, storage_key=storage_key, size=size, sha256=actual)
        now = time.time()
        conn.execute(
            "UPDATE asset_uploads SET state='committed',object_version_id=?,updated_at=?,completed_at=? "
            "WHERE id=?", (version["id"], now, now, upload_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    shutil.rmtree(directory, ignore_errors=True)
    return {"upload": upload_status(upload_id, owner_id), "object_version": version, "duplicate": False}


def abort_upload(upload_id: str, owner_id: str) -> bool:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT asset_id FROM asset_uploads WHERE id=? AND owner_id=? AND state='uploading'",
        (upload_id, owner_id),
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE asset_uploads SET state='aborted',updated_at=?,expires_at=? WHERE id=?",
        (time.time(), time.time(), upload_id),
    )
    conn.commit()
    shutil.rmtree(_upload_dir(upload_id), ignore_errors=True)
    return True


def create_download_grant(asset: dict[str, Any]) -> dict[str, Any]:
    row = db.get_conn().execute(
        "SELECT * FROM asset_object_versions WHERE asset_id=? AND deleted_at=0 "
        "ORDER BY version_number DESC LIMIT 1", (asset["id"],),
    ).fetchone()
    if not row:
        raise ObjectConflict("asset has no committed object")
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + settings.ASSET_DOWNLOAD_GRANT_TTL_SECONDS
    db.get_conn().execute(
        "INSERT INTO asset_download_grants "
        "(token_hash,asset_id,object_version_id,owner_id,expires_at,created_at) VALUES (?,?,?,?,?,?)",
        (hashlib.sha256(token.encode()).hexdigest(), asset["id"], row["id"], asset["owner_id"], expires_at, now),
    )
    db.get_conn().commit()
    return {"token": token, "expires_at": expires_at, "object_version": dict(row)}


def authorize_download(asset_id: str, token: str) -> tuple[dict[str, Any], Path]:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = db.get_conn()
    row = conn.execute(
        "SELECT g.*,v.storage_key,v.size,v.sha256,a.name FROM asset_download_grants g "
        "JOIN asset_object_versions v ON v.id=g.object_version_id AND v.deleted_at=0 "
        "JOIN business_assets a ON a.id=g.asset_id AND a.deleted_at=0 "
        "JOIN accounts ac ON ac.id=g.owner_id AND ac.suspended_at=0 "
        "WHERE g.token_hash=? AND g.asset_id=? AND g.expires_at>?",
        (token_hash, asset_id, time.time()),
    ).fetchone()
    if not row:
        raise KeyError(asset_id)
    conn.execute(
        "UPDATE asset_download_grants SET used_at=CASE WHEN used_at=0 THEN ? ELSE used_at END WHERE token_hash=?",
        (time.time(), token_hash),
    )
    conn.commit()
    result = dict(row)
    path = object_path(str(result["storage_key"]))
    if not path.is_file() or path.stat().st_size != int(result["size"]):
        raise ObjectConflict("asset object is unavailable")
    return result, path


def cleanup_expired() -> dict[str, int]:
    now = time.time()
    conn = db.get_conn()
    upload_ids = [str(row[0]) for row in conn.execute(
        "SELECT id FROM asset_uploads WHERE state='uploading' AND expires_at<=?", (now,),
    ).fetchall()]
    for upload_id in upload_ids:
        shutil.rmtree(_upload_dir(upload_id), ignore_errors=True)
    conn.executemany(
        "UPDATE asset_uploads SET state='expired',updated_at=? WHERE id=?",
        [(now, upload_id) for upload_id in upload_ids],
    )
    grants = conn.execute("DELETE FROM asset_download_grants WHERE expires_at<=?", (now,)).rowcount
    conn.commit()
    return {"uploads": len(upload_ids), "grants": int(grants)}
