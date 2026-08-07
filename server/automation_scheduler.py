"""Server-owned automation scheduling that enqueues Local Agent Runs."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import time
from typing import Any

import business_store
import db


SCAN_SECONDS = 10
log = logging.getLogger("agentmate.automation-scheduler")


def next_run_at(kind: str, interval_min: int, at_time: str, now: float) -> float | None:
    if kind == "webhook":
        return None
    if kind in {"daily", "health_daily"}:
        try:
            hour, minute = (int(value) for value in at_time.split(":", 1))
        except (AttributeError, ValueError):
            hour, minute = 9, 0
        target = dt.datetime.fromtimestamp(now).replace(
            hour=hour % 24, minute=minute % 60, second=0, microsecond=0,
        )
        if target.timestamp() <= now:
            target += dt.timedelta(days=1)
        return target.timestamp()
    return now + max(1, int(interval_min)) * 60


def _hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def enqueue_automation(
    automation: dict[str, Any], *, fire_key: str, planned_at: float,
) -> dict[str, Any]:
    owner_id = str(automation["owner_id"])
    automation_id = str(automation["id"])
    project_id = str(automation.get("project_id") or "") or None
    now = time.time()
    conn = db.get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO business_automation_fires "
        "(id,automation_id,owner_id,fire_key,trigger_kind,planned_at,status,attempt,max_attempts,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,'queued',0,?,?,?)",
        (
            db.new_uuid(), automation_id, owner_id, fire_key,
            "manual" if fire_key.startswith("manual:") else str(automation.get("trigger_kind") or "scheduled"),
            planned_at, max(1, int(automation.get("max_attempts") or 3)), now, now,
        ),
    )
    fire_row = conn.execute(
        "SELECT * FROM business_automation_fires WHERE automation_id=? AND fire_key=?",
        (automation_id, fire_key),
    ).fetchone()
    if fire_row is None:
        raise RuntimeError("automation fire could not be initialized")
    fire = dict(fire_row)
    conn.commit()
    if fire.get("run_id") and str(fire.get("status")) not in {"retry_wait"}:
        session = business_store.get_record("business_sessions", str(fire["session_id"]))
        run = business_store.get_record("business_runs", str(fire["run_id"]))
        message = conn.execute(
            "SELECT * FROM business_messages WHERE run_id=? AND role='user' ORDER BY sequence LIMIT 1",
            (fire["run_id"],),
        ).fetchone()
        return {
            "session": session, "user_message": business_store.decode_row(message), "run": run,
            "fire": fire, "duplicate": True,
        }
    attempt = int(fire.get("attempt") or 0) + 1
    if attempt > int(fire.get("max_attempts") or 1):
        raise RuntimeError("automation fire exhausted its retry budget")
    request_key = f"automation-fire:{fire['id']}:attempt:{attempt}"
    request_snapshot = {
        "automation_id": automation_id,
        "automation_fire_id": str(fire["id"]),
        "automation_fire_key": fire_key,
        "automation_attempt": attempt,
        "planned_at": planned_at,
        "loadout": {"experts": [], "skills": [], "skill_bundles": [], "connectors": [], "knowledge_ids": []},
        "refs": [],
    }
    signature = {
        "automation_id": automation_id, "fire_key": fire_key,
        "prompt": automation["prompt"], "model_ref": automation.get("model_ref"),
        "project_id": project_id,
    }
    session, message, run, duplicate = business_store.create_turn(
        actor_id=owner_id, owner_id=owner_id, project_id=project_id, session_id=None,
        session_title=str(automation["name"])[:500], session_kind="automation", session_space=None,
        user_text=str(automation["prompt"]), client_request_id=request_key, request_hash=_hash(signature),
        run_fields={
            "work_item_id": None, "mode": "exec",
            "workspace": f"project:{project_id}" if project_id else "default",
            "retry_of": fire.get("run_id"), "model_ref": automation.get("model_ref"), "model_id": None,
            "model_snapshot": {},
            "permission_snapshot": {
                "execution_source": "background",
                "preauthorized_permissions": automation.get("preauthorized_permissions") or [],
                "timeout_sec": int(automation.get("timeout_sec") or 300),
                "max_total_tokens": int(automation.get("max_total_tokens") or 0),
            },
            "target_device_id": "",
            "required_capabilities": ["run_events_v1", "llm.chat", "agent.tools"],
            "request_snapshot": request_snapshot, "max_recoveries": 3,
        },
    )
    previous_run_id = str(fire.get("run_id") or "") or None
    conn.execute(
        "UPDATE business_automation_fires SET status='queued',attempt=?,session_id=?,run_id=?,"
        "retry_of_run_id=?,error_code='',error_message='',next_attempt_at=NULL,updated_at=?,finished_at=0 WHERE id=?",
        (attempt, session["id"], run["id"], previous_run_id, now, fire["id"]),
    )
    conn.execute(
        "UPDATE business_automations SET last_run_at=?,last_session_id=?,last_status='queued',"
        "updated_at=?,version=version+1 WHERE id=? AND deleted_at=0",
        (now, session["id"], now, automation_id),
    )
    conn.commit()
    fire = dict(conn.execute("SELECT * FROM business_automation_fires WHERE id=?", (fire["id"],)).fetchone())
    return {"session": session, "user_message": message, "run": run, "fire": fire, "duplicate": duplicate}


def finish_run(
    conn, *, run_id: str, owner_id: str, failed: bool, error_code: str,
    error_message: str, prompt_tokens: int, completion_tokens: int, now: float,
) -> None:
    """Commit retry/dead-letter state in the same transaction as Run terminal state."""
    row = conn.execute(
        "SELECT f.*,a.retry_backoff_sec FROM business_automation_fires f "
        "JOIN business_automations a ON a.id=f.automation_id "
        "WHERE f.run_id=? AND f.owner_id=?",
        (run_id, owner_id),
    ).fetchone()
    if row is None:
        return
    fire = dict(row)
    if not failed:
        status, next_attempt_at, finished_at, automation_status = "succeeded", None, now, "ok"
    elif int(fire["attempt"]) < int(fire["max_attempts"]):
        delay = int(fire.get("retry_backoff_sec") or 30) * (2 ** max(0, int(fire["attempt"]) - 1))
        status, next_attempt_at, finished_at, automation_status = "retry_wait", now + delay, 0, "retrying"
    else:
        status, next_attempt_at, finished_at, automation_status = "dead_letter", None, now, "error"
    conn.execute(
        "UPDATE business_automation_fires SET status=?,error_code=?,error_message=?,prompt_tokens=?,"
        "completion_tokens=?,next_attempt_at=?,updated_at=?,finished_at=? WHERE id=?",
        (
            status, error_code[:200], error_message[:20000], prompt_tokens, completion_tokens,
            next_attempt_at, now, finished_at, fire["id"],
        ),
    )
    conn.execute(
        "UPDATE business_automations SET last_status=?,updated_at=?,version=version+1 "
        "WHERE id=? AND owner_id=? AND deleted_at=0",
        (automation_status, now, fire["automation_id"], owner_id),
    )


def scan_once(now: float | None = None) -> int:
    now = time.time() if now is None else now
    conn = db.get_conn()
    due = conn.execute(
        "SELECT * FROM business_automations WHERE deleted_at=0 AND enabled=1 "
        "AND trigger_kind!='webhook' AND next_run_at IS NOT NULL AND next_run_at<=? "
        "ORDER BY next_run_at,id LIMIT 100",
        (now,),
    ).fetchall()
    enqueued = 0
    for row in due:
        automation = business_store.decode_row(row) or {}
        planned_at = float(automation.get("next_run_at") or now)
        fire_key = f"scheduled:{int(planned_at * 1000)}"
        try:
            enqueue_automation(automation, fire_key=fire_key, planned_at=planned_at)
        except Exception:  # noqa: BLE001 - one automation must not stop the scheduler
            log.exception("failed to enqueue automation %s", automation.get("id"))
            continue
        following = next_run_at(
            str(automation.get("trigger_kind") or "interval"),
            int(automation.get("interval_min") or 60), str(automation.get("at_time") or "09:00"), now,
        )
        conn.execute(
            "UPDATE business_automations SET next_run_at=?,updated_at=?,version=version+1 "
            "WHERE id=? AND next_run_at=? AND deleted_at=0",
            (following, now, automation["id"], planned_at),
        )
        conn.commit()
        enqueued += 1
    retries = conn.execute(
        "SELECT f.id AS fire_id,f.automation_id,f.fire_key,f.planned_at "
        "FROM business_automation_fires f "
        "JOIN business_automations a ON a.id=f.automation_id "
        "WHERE f.status='retry_wait' AND f.next_attempt_at IS NOT NULL AND f.next_attempt_at<=? "
        "AND a.deleted_at=0 AND a.enabled=1 ORDER BY f.next_attempt_at,f.id LIMIT 100",
        (now,),
    ).fetchall()
    for row in retries:
        values = dict(row)
        try:
            automation = business_store.get_record("business_automations", str(values["automation_id"]))
            if automation is None:
                continue
            enqueue_automation(
                automation, fire_key=str(values["fire_key"]), planned_at=float(values["planned_at"]),
            )
            enqueued += 1
        except Exception:  # noqa: BLE001
            log.exception("failed to retry automation fire %s", values.get("fire_id"))
    return enqueued


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(scan_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("automation scheduler scan failed")
        await asyncio.sleep(SCAN_SECONDS)
