"""Owner-scoped named Skill bundles with deterministic, transparent expansion."""
from __future__ import annotations

import json
import time
from typing import Any

from storage import db


def _init() -> None:
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS skill_bundles (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            skills TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner_id,name)
        );
        CREATE INDEX IF NOT EXISTS idx_skill_bundles_owner
            ON skill_bundles(owner_id,updated_at DESC);
        """
    )
    conn.commit()


def _skills(value: str) -> list[str]:
    try:
        raw = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["skills"] = _skills(item["skills"])
    return item


def _normalize_skills(skills: list[str]) -> list[str]:
    result: list[str] = []
    for raw in skills:
        value = str(raw).strip()
        if value and value not in result:
            result.append(value)
    if not result:
        raise ValueError("bundle 至少包含一个 Skill")
    if len(result) > 50:
        raise ValueError("bundle 最多包含 50 个 Skill")
    return result


def create(owner_id: str, name: str, description: str, skills: list[str]) -> dict[str, Any]:
    _init()
    name = (name or "").strip()
    description = (description or "").strip()
    if not name or len(name) > 120 or len(description) > 500:
        raise ValueError("bundle 名称为空或字段过长")
    normalized = _normalize_skills(skills)
    now = time.time()
    bundle_id = db.new_uuid()
    try:
        db.get_conn().execute(
            """INSERT INTO skill_bundles
               (id,owner_id,name,description,skills,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                bundle_id, owner_id, name, description,
                json.dumps(normalized, ensure_ascii=False), now, now,
            ),
        )
        db.get_conn().commit()
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise ValueError("bundle 名称已存在") from exc
        raise
    return get(bundle_id, owner_id)  # type: ignore[return-value]


def get(bundle_id: str, owner_id: str) -> dict[str, Any] | None:
    _init()
    row = db.get_conn().execute(
        "SELECT * FROM skill_bundles WHERE id=? AND owner_id=?",
        (bundle_id, owner_id),
    ).fetchone()
    return _row(row) if row else None


def list_bundles(owner_id: str) -> list[dict[str, Any]]:
    _init()
    rows = db.get_conn().execute(
        "SELECT * FROM skill_bundles WHERE owner_id=? ORDER BY name COLLATE NOCASE,id",
        (owner_id,),
    ).fetchall()
    return [_row(row) for row in rows]


def update(
    bundle_id: str,
    owner_id: str,
    *,
    name: str,
    description: str,
    skills: list[str],
) -> dict[str, Any]:
    if not get(bundle_id, owner_id):
        raise KeyError(bundle_id)
    name = (name or "").strip()
    description = (description or "").strip()
    if not name or len(name) > 120 or len(description) > 500:
        raise ValueError("bundle 名称为空或字段过长")
    normalized = _normalize_skills(skills)
    try:
        db.get_conn().execute(
            """UPDATE skill_bundles
               SET name=?,description=?,skills=?,updated_at=? WHERE id=? AND owner_id=?""",
            (
                name, description, json.dumps(normalized, ensure_ascii=False),
                time.time(), bundle_id, owner_id,
            ),
        )
        db.get_conn().commit()
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise ValueError("bundle 名称已存在") from exc
        raise
    return get(bundle_id, owner_id)  # type: ignore[return-value]


def delete(bundle_id: str, owner_id: str) -> bool:
    _init()
    cur = db.get_conn().execute(
        "DELETE FROM skill_bundles WHERE id=? AND owner_id=?",
        (bundle_id, owner_id),
    )
    db.get_conn().commit()
    return bool(cur.rowcount)


def resolve(owner_id: str, bundle_ids: list[str]) -> dict[str, Any]:
    """Expand bundles in caller order, then Skill order, without hiding misses."""
    from agent import skills_store

    _init()
    installed = {
        str(item.get("slug") or item.get("key") or ""): item
        for item in skills_store.scan(owner_id)
    }
    aliases: dict[str, set[str]] = {}
    for slug, item in installed.items():
        for alias in {
            slug,
            str(item.get("key") or ""),
            str(item.get("name") or ""),
        }:
            if alias:
                aliases.setdefault(alias, set()).add(slug)
    ordered: list[str] = []
    missing_bundles: list[str] = []
    missing_skills: list[dict[str, str]] = []
    resolved_bundles: list[dict[str, Any]] = []
    for bundle_id in dict.fromkeys(str(item).strip() for item in bundle_ids if str(item).strip()):
        bundle = get(bundle_id, owner_id)
        if not bundle:
            missing_bundles.append(bundle_id)
            continue
        resolved_bundles.append({
            "id": bundle["id"], "name": bundle["name"], "skills": list(bundle["skills"]),
        })
        for raw in bundle["skills"]:
            matches = aliases.get(raw, set())
            slug = next(iter(matches)) if len(matches) == 1 else None
            if not slug or slug not in installed:
                missing_skills.append({
                    "bundle_id": bundle["id"],
                    "bundle_name": bundle["name"],
                    "skill": raw,
                })
                continue
            if slug not in ordered:
                ordered.append(slug)
    return {
        "skills": ordered,
        "bundles": resolved_bundles,
        "missing_bundles": missing_bundles,
        "missing_skills": missing_skills,
    }
