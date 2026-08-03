"""Owner-scoped, privacy-minimal Skill usage telemetry and governance (WB-337)."""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
import time
from typing import Any

from storage import db

EVENTS = {"offered", "discovered", "loaded", "run_succeeded", "run_failed", "disabled", "enabled"}
RATINGS = {"helpful", "neutral", "not_helpful"}
_owner_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("skill_usage_owner", default="")
_run_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("skill_usage_run", default="")


def _init() -> None:
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS skill_usage_events (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            release_id TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            event TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_usage_dedupe
            ON skill_usage_events(owner_id,release_id,run_id,event);
        CREATE INDEX IF NOT EXISTS idx_skill_usage_owner_release
            ON skill_usage_events(owner_id,release_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS skill_usage_ratings (
            owner_id TEXT NOT NULL,
            release_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            rating TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY(owner_id,release_id)
        );
        CREATE TABLE IF NOT EXISTS skill_governance_ignores (
            owner_id TEXT NOT NULL,
            suggestion_id TEXT NOT NULL,
            ignored_at REAL NOT NULL,
            PRIMARY KEY(owner_id,suggestion_id)
        );
        """
    )
    conn.commit()


def set_context(owner_id: str, run_id: str) -> None:
    _owner_ctx.set((owner_id or "").strip())
    _run_ctx.set((run_id or "").strip())


def clear_context() -> None:
    _owner_ctx.set("")
    _run_ctx.set("")


def context_snapshot() -> dict[str, str]:
    return {"owner_id": _owner_ctx.get(), "run_id": _run_ctx.get()}


def identity(item: dict[str, Any]) -> str:
    release_id = str(item.get("release_id") or "").strip()
    if release_id:
        return release_id
    content_hash = str(item.get("content_hash") or "").strip()
    if content_hash:
        return f"local:{content_hash}"
    return f"slug:{str(item.get('slug') or item.get('key') or '').strip()}"


def record(
    event: str,
    item: dict[str, Any],
    *,
    owner_id: str = "",
    run_id: str = "",
) -> None:
    """Record identity-only telemetry; no prompt, arguments, files or Skill body."""
    if event not in EVENTS:
        raise ValueError(f"invalid Skill usage event: {event}")
    owner = (owner_id or _owner_ctx.get()).strip()
    slug = str(item.get("slug") or item.get("key") or "").strip()
    release_id = identity(item)
    run = (run_id or _run_ctx.get()).strip()
    if not owner or not slug or not release_id:
        return
    _init()
    # Run-scoped discovery/load/result events are idempotent.  User lifecycle
    # events have no Run, so their timestamp participates in the key.
    nonce = run if run else f"{time.time_ns()}"
    event_id = hashlib.sha256(
        f"{owner}\0{release_id}\0{nonce}\0{event}".encode("utf-8")
    ).hexdigest()
    db.get_conn().execute(
        """INSERT OR IGNORE INTO skill_usage_events
           (id,owner_id,slug,release_id,content_hash,run_id,event,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            event_id, owner, slug, release_id, str(item.get("content_hash") or ""),
            run, event, time.time(),
        ),
    )
    db.get_conn().commit()


def record_many(event: str, items: list[dict[str, Any]], *, owner_id: str, run_id: str) -> None:
    for item in items:
        record(event, item, owner_id=owner_id, run_id=run_id)


def rate(owner_id: str, item: dict[str, Any], rating: str) -> dict[str, Any]:
    value = (rating or "").strip().lower()
    if value not in RATINGS:
        raise ValueError("rating must be helpful, neutral or not_helpful")
    _init()
    release_id = identity(item)
    slug = str(item.get("slug") or item.get("key") or "")
    db.get_conn().execute(
        """INSERT INTO skill_usage_ratings (owner_id,release_id,slug,rating,updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(owner_id,release_id) DO UPDATE SET
             slug=excluded.slug,rating=excluded.rating,updated_at=excluded.updated_at""",
        (owner_id, release_id, slug, value, time.time()),
    )
    db.get_conn().commit()
    return {"slug": slug, "release_id": release_id, "rating": value}


def summaries(owner_id: str) -> list[dict[str, Any]]:
    from agent import skills_store

    _init()
    rows = db.get_conn().execute(
        """SELECT release_id,slug,
                  SUM(CASE WHEN event='offered' THEN 1 ELSE 0 END) AS offers,
                  SUM(CASE WHEN event='discovered' THEN 1 ELSE 0 END) AS discoveries,
                  SUM(CASE WHEN event='loaded' THEN 1 ELSE 0 END) AS loads,
                  SUM(CASE WHEN event='run_succeeded' THEN 1 ELSE 0 END) AS successes,
                  SUM(CASE WHEN event='run_failed' THEN 1 ELSE 0 END) AS failures,
                  SUM(CASE WHEN event='disabled' THEN 1 ELSE 0 END) AS disables,
                  MAX(CASE WHEN event='loaded' THEN created_at END) AS last_loaded_at,
                  MAX(created_at) AS last_event_at
           FROM skill_usage_events WHERE owner_id=? GROUP BY release_id,slug""",
        (owner_id,),
    ).fetchall()
    metrics = {row["release_id"]: dict(row) for row in rows}
    ratings = {
        row["release_id"]: dict(row)
        for row in db.get_conn().execute(
            "SELECT * FROM skill_usage_ratings WHERE owner_id=?", (owner_id,)
        ).fetchall()
    }
    result: list[dict[str, Any]] = []
    for item in skills_store.scan(owner_id):
        release_id = identity(item)
        metric = metrics.get(release_id, {})
        successes = int(metric.get("successes") or 0)
        failures = int(metric.get("failures") or 0)
        runs = successes + failures
        result.append({
            "slug": str(item.get("slug") or item.get("key") or ""),
            "name": str(item.get("name") or ""),
            "release_id": release_id,
            "content_hash": str(item.get("content_hash") or ""),
            "disabled": bool(item.get("disabled")),
            "installed_at": float(item.get("installed_at") or 0),
            "offers": int(metric.get("offers") or 0),
            "discoveries": int(metric.get("discoveries") or 0),
            "loads": int(metric.get("loads") or 0),
            "successes": successes,
            "failures": failures,
            "success_rate": round(successes / runs, 4) if runs else None,
            "last_loaded_at": metric.get("last_loaded_at"),
            "last_event_at": metric.get("last_event_at"),
            "rating": (ratings.get(release_id) or {}).get("rating"),
        })
    return sorted(result, key=lambda item: item["name"].casefold())


def _suggestion_id(owner_id: str, reason: str, slugs: list[str]) -> str:
    return hashlib.sha256(
        f"{owner_id}\0{reason}\0{'|'.join(sorted(slugs))}".encode("utf-8")
    ).hexdigest()[:24]


def suggestions(owner_id: str, *, now: float | None = None) -> list[dict[str, Any]]:
    """Explain deterministic cleanup candidates; action is always advisory."""
    _init()
    current = time.time() if now is None else float(now)
    ignored = {
        row["suggestion_id"]
        for row in db.get_conn().execute(
            "SELECT suggestion_id FROM skill_governance_ignores WHERE owner_id=?",
            (owner_id,),
        ).fetchall()
    }
    result: list[dict[str, Any]] = []
    metrics = summaries(owner_id)
    for item in metrics:
        if item["disabled"]:
            continue
        reason = ""
        explanation = ""
        installed_at = float(item.get("installed_at") or 0)
        last_loaded = float(item.get("last_loaded_at") or 0)
        runs = int(item["successes"]) + int(item["failures"])
        if item["loads"] == 0 and installed_at and current - installed_at >= 30 * 86400:
            reason = "never_loaded"
            explanation = "安装已满 30 天，但从未被显式加载"
        elif last_loaded and current - last_loaded >= 90 * 86400:
            reason = "stale"
            explanation = "最近一次显式加载已超过 90 天"
        elif runs >= 5 and float(item.get("success_rate") or 0) < 0.4:
            reason = "low_success"
            explanation = f"最近累计 {runs} 次归因 Run，成功率低于 40%"
        elif item.get("rating") == "not_helpful":
            reason = "not_helpful"
            explanation = "你已将此 release 评价为无帮助"
        if not reason:
            continue
        suggestion_id = _suggestion_id(owner_id, reason, [item["slug"]])
        if suggestion_id in ignored:
            continue
        result.append({
            "id": suggestion_id,
            "reason": reason,
            "slugs": [item["slug"]],
            "release_ids": [item["release_id"]],
            "explanation": explanation,
            "recommended_action": "disable",
            "automatic_action": False,
        })

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in metrics:
        normalized = re.sub(r"\W+", "", item["name"].casefold())
        if normalized:
            by_name.setdefault(normalized, []).append(item)
    for duplicates in by_name.values():
        if len(duplicates) < 2:
            continue
        slugs = sorted(item["slug"] for item in duplicates)
        suggestion_id = _suggestion_id(owner_id, "duplicate_name", slugs)
        if suggestion_id in ignored:
            continue
        result.append({
            "id": suggestion_id,
            "reason": "duplicate_name",
            "slugs": slugs,
            "release_ids": sorted(item["release_id"] for item in duplicates),
            "explanation": "多个已安装 Skill 使用相同名称，建议人工复核是否保留全部",
            "recommended_action": "review",
            "automatic_action": False,
        })
    return sorted(result, key=lambda item: (item["reason"], item["slugs"]))


def ignore_suggestion(owner_id: str, suggestion_id: str) -> None:
    value = (suggestion_id or "").strip()
    if not re.fullmatch(r"[a-f0-9]{24}", value):
        raise ValueError("invalid suggestion id")
    _init()
    db.get_conn().execute(
        """INSERT OR REPLACE INTO skill_governance_ignores
           (owner_id,suggestion_id,ignored_at) VALUES (?,?,?)""",
        (owner_id, value, time.time()),
    )
    db.get_conn().commit()
