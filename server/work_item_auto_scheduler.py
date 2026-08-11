"""One-shot, gate-driven WorkItem execution scheduler (WB-502)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import business_store
import db
import run_protocol_store


log = logging.getLogger("agentmate.work-item-auto-scheduler")
POLL_SECONDS = 2.0
CORE_CAPABILITIES = ("run_events_v1", "llm.chat", "agent.tools")
SAFE_BACKGROUND_PERMISSIONS = {"workspace.read", "workspace.write"}
ACTIVE_RUN_STATUSES = {"queued", "leased", "running", "waiting_user", "paused", "recoverable"}
SUCCESS_RUN_STATUSES = {"completed", "succeeded"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def _row(row: Any) -> dict[str, Any]:
    value = dict(row)
    value["required_capabilities"] = _decode(value.get("required_capabilities"), [])
    value["preauthorized_permissions"] = _decode(value.get("preauthorized_permissions"), [])
    return value


def default_policy(work_item_id: str, project_id: str) -> dict[str, Any]:
    return {
        "work_item_id": work_item_id,
        "project_id": project_id,
        "execution_owner_id": "",
        "mode": "manual",
        "routing_mode": "any_compatible",
        "target_device_id": "",
        "required_capabilities": list(CORE_CAPABILITIES),
        "model_ref": None,
        "timeout_sec": 300,
        "max_attempts": 1,
        "retry_backoff_sec": 30,
        "max_total_tokens": 0,
        "notify_policy": "failure,recovery",
        "preauthorized_permissions": ["workspace.write"],
        "version": 0,
        "state": "manual",
        "blocker_code": "",
        "blocker_message": "",
        "last_run_id": "",
        "last_trigger_key": "",
        "last_attempt": 0,
        "updated_at": 0,
    }


def get_policy(work_item_id: str, project_id: str = "") -> dict[str, Any]:
    row = db.get_conn().execute(
        "SELECT p.*,a.name AS execution_owner_name FROM work_item_execution_policies p "
        "LEFT JOIN accounts a ON a.id=p.execution_owner_id WHERE p.work_item_id=?",
        (work_item_id,),
    ).fetchone()
    return _row(row) if row is not None else default_policy(work_item_id, project_id)


def _normalized_policy(values: dict[str, Any]) -> dict[str, Any]:
    mode = str(values.get("mode") or "manual")
    routing_mode = str(values.get("routing_mode") or "any_compatible")
    target_device_id = str(values.get("target_device_id") or "")
    required = list(dict.fromkeys(str(item) for item in values.get("required_capabilities") or CORE_CAPABILITIES))
    permissions = list(dict.fromkeys(str(item) for item in values.get("preauthorized_permissions") or []))
    if mode not in {"manual", "auto"}:
        raise ValueError("mode must be 'manual' or 'auto'")
    if routing_mode not in {"any_compatible", "specific"}:
        raise ValueError("routing_mode must be 'any_compatible' or 'specific'")
    if mode == "auto" and not set(CORE_CAPABILITIES).issubset(required):
        raise ValueError("auto execution requires the core Local Agent capabilities")
    if routing_mode == "any_compatible":
        target_device_id = ""
    elif not target_device_id:
        raise ValueError("specific routing requires target_device_id")
    return {
        "mode": mode,
        "routing_mode": routing_mode,
        "target_device_id": target_device_id,
        "required_capabilities": required,
        "model_ref": str(values.get("model_ref") or "") or None,
        "timeout_sec": max(1, min(3600, int(values.get("timeout_sec") or 300))),
        "max_attempts": max(1, min(10, int(values.get("max_attempts") or 1))),
        "retry_backoff_sec": max(1, min(86400, int(values.get("retry_backoff_sec") or 30))),
        "max_total_tokens": max(0, min(10_000_000, int(values.get("max_total_tokens") or 0))),
        "notify_policy": str(values.get("notify_policy") or "failure,recovery")[:200],
        "preauthorized_permissions": permissions,
    }


def configure_policy(
    *, work_item: dict[str, Any], execution_owner_id: str, values: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    normalized = _normalized_policy(values)
    if normalized["routing_mode"] == "specific":
        target = db.get_conn().execute(
            "SELECT owner_id,status,authenticated_at,revoked_at FROM agent_devices WHERE id=?",
            (normalized["target_device_id"],),
        ).fetchone()
        if (
            target is None or str(target["owner_id"]) != execution_owner_id
            or str(target["status"]) != "active"
            or float(target["authenticated_at"] or 0) <= 0
            or float(target["revoked_at"] or 0) > 0
        ):
            raise ValueError("target device must be an active verified device owned by the execution owner")
    conn = db.get_conn()
    existing_row = conn.execute(
        "SELECT * FROM work_item_execution_policies WHERE work_item_id=?",
        (work_item["id"],),
    ).fetchone()
    existing = _row(existing_row) if existing_row is not None else None
    comparable = {
        **normalized,
        "execution_owner_id": execution_owner_id,
        "project_id": str(work_item["project_id"]),
    }
    if existing and all(existing.get(key) == value for key, value in comparable.items()):
        return existing, False
    now = time.time()
    version = int(existing.get("version") or 0) + 1 if existing else 1
    state = "manual" if normalized["mode"] == "manual" else "evaluating"
    conn.execute(
        "INSERT INTO work_item_execution_policies "
        "(work_item_id,project_id,execution_owner_id,mode,routing_mode,target_device_id,"
        "required_capabilities,model_ref,timeout_sec,max_attempts,retry_backoff_sec,max_total_tokens,"
        "notify_policy,preauthorized_permissions,version,state,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(work_item_id) DO UPDATE SET project_id=excluded.project_id,"
        "execution_owner_id=excluded.execution_owner_id,mode=excluded.mode,"
        "routing_mode=excluded.routing_mode,target_device_id=excluded.target_device_id,"
        "required_capabilities=excluded.required_capabilities,model_ref=excluded.model_ref,"
        "timeout_sec=excluded.timeout_sec,max_attempts=excluded.max_attempts,"
        "retry_backoff_sec=excluded.retry_backoff_sec,max_total_tokens=excluded.max_total_tokens,"
        "notify_policy=excluded.notify_policy,preauthorized_permissions=excluded.preauthorized_permissions,"
        "version=excluded.version,state=excluded.state,blocker_code='',blocker_message='',"
        "last_run_id='',last_trigger_key='',last_attempt=0,updated_at=excluded.updated_at",
        (
            work_item["id"], work_item["project_id"], execution_owner_id,
            normalized["mode"], normalized["routing_mode"], normalized["target_device_id"],
            _json(normalized["required_capabilities"]), normalized["model_ref"],
            normalized["timeout_sec"], normalized["max_attempts"], normalized["retry_backoff_sec"],
            normalized["max_total_tokens"], normalized["notify_policy"],
            _json(normalized["preauthorized_permissions"]), version, state, now, now,
        ),
    )
    conn.commit()
    return get_policy(str(work_item["id"]), str(work_item["project_id"])), True


def _gate(
    policy: dict[str, Any], item: dict[str, Any], now: float, *, retrying: bool = False,
) -> tuple[str, str]:
    runnable = {"todo", "doing"}
    if retrying:
        runnable.add("paused")
    if str(item.get("status") or "") not in runnable:
        return "work_item_not_runnable", "任务必须处于待办或进行中状态"
    dependencies = list(item.get("dependency_ids") or [])
    if dependencies:
        placeholders = ",".join("?" for _ in dependencies)
        pending = db.get_conn().execute(
            f"SELECT title FROM work_items WHERE project_id=? AND id IN ({placeholders}) AND status!='done' "
            "ORDER BY sort,id LIMIT 1",
            (item["project_id"], *dependencies),
        ).fetchone()
        if pending is not None:
            return "dependency_incomplete", f"依赖任务尚未完成：{pending['title']}"
    sprint_id = str(item.get("sprint_id") or "")
    if sprint_id:
        sprint = db.get_conn().execute(
            "SELECT status,name FROM sprints WHERE id=? AND project_id=?",
            (sprint_id, item["project_id"]),
        ).fetchone()
        if sprint is None or str(sprint["status"]) != "active":
            return "sprint_inactive", f"所属 Sprint 尚未激活：{str(sprint['name']) if sprint else sprint_id}"
    permissions = set(policy.get("preauthorized_permissions") or [])
    if "workspace.write" not in permissions:
        return "permission_missing", "缺少无人值守执行所需的 workspace.write 预授权"
    if permissions - SAFE_BACKGROUND_PERMISSIONS:
        return "high_risk_permission", "策略包含未获准的高风险后台权限"
    owner_id = str(policy["execution_owner_id"])
    owner_access = db.get_conn().execute(
        "SELECT 1 FROM projects p LEFT JOIN project_members pm "
        "ON pm.project_id=p.id AND pm.account_id=? "
        "WHERE p.id=? AND (p.owner_id=? OR pm.account_id IS NOT NULL)",
        (owner_id, item["project_id"], owner_id),
    ).fetchone()
    if owner_access is None:
        return "execution_owner_unavailable", "执行负责人已不是项目成员"
    target = str(policy.get("target_device_id") or "")
    params: list[Any] = [owner_id]
    target_clause = ""
    if target:
        target_clause = " AND id=?"
        params.append(target)
    rows = db.get_conn().execute(
        "SELECT id,capabilities,last_seen_at FROM agent_devices WHERE owner_id=? AND status='active' "
        "AND authenticated_at>0 AND revoked_at=0" + target_clause,
        params,
    ).fetchall()
    if not rows:
        return "device_unavailable", "没有可用的已验证 Local Agent"
    required = set(policy.get("required_capabilities") or [])
    compatible = [
        row for row in rows
        if required.issubset(run_protocol_store._capability_set(_decode(row["capabilities"], {})))
    ]
    if not compatible:
        return "capability_mismatch", "Local Agent 缺少任务所需能力"
    online = [
        row for row in compatible
        if float(row["last_seen_at"] or 0) >= now - run_protocol_store.DEVICE_ONLINE_WINDOW_SECONDS
    ]
    if not online:
        return "device_offline", "目标 Local Agent 已离线"
    available = []
    for row in online:
        capabilities = _decode(row["capabilities"], {})
        active = int(db.get_conn().execute(
            "SELECT COUNT(*) FROM run_leases l JOIN business_runs r ON r.id=l.run_id "
            "WHERE l.device_id=? AND l.owner_id=? AND l.status='active' AND l.expires_at>? "
            "AND r.status IN ('leased','running')",
            (row["id"], owner_id, now),
        ).fetchone()[0])
        resident = int(db.get_conn().execute(
            "SELECT COUNT(*) FROM run_leases l JOIN business_runs r ON r.id=l.run_id "
            "WHERE l.device_id=? AND l.owner_id=? AND l.status='active' AND l.expires_at>? "
            "AND r.status IN ('leased','running','waiting_user','paused')",
            (row["id"], owner_id, now),
        ).fetchone()[0])
        if (
            active < run_protocol_store._parallel_capacity(capabilities)
            and resident < run_protocol_store._resident_capacity(capabilities)
        ):
            available.append(row)
    if not available:
        return "device_busy", "兼容 Local Agent 的执行容量已满"
    workspace_blocker = db.get_conn().execute(
        "SELECT r.id FROM run_leases l JOIN business_runs r ON r.id=l.run_id "
        "WHERE l.owner_id=? AND l.status='active' AND l.expires_at>? "
        "AND r.project_id=? AND r.status IN ('leased','running','waiting_user','paused') LIMIT 1",
        (owner_id, now, item["project_id"]),
    ).fetchone()
    if workspace_blocker is not None:
        return "resource_lock_wait", "同一项目工作区已有写入任务，等待其释放写锁"
    return "", ""


def _update_state(
    conn, work_item_id: str, *, state: str, blocker_code: str = "",
    blocker_message: str = "", last_run_id: str | None = None,
    last_trigger_key: str | None = None, last_attempt: int | None = None,
) -> None:
    fields = ["state=?", "blocker_code=?", "blocker_message=?", "updated_at=?"]
    values: list[Any] = [state, blocker_code, blocker_message, time.time()]
    for column, value in (
        ("last_run_id", last_run_id),
        ("last_trigger_key", last_trigger_key),
        ("last_attempt", last_attempt),
    ):
        if value is not None:
            fields.append(f"{column}=?")
            values.append(value)
    values.append(work_item_id)
    conn.execute(
        f"UPDATE work_item_execution_policies SET {','.join(fields)} WHERE work_item_id=?",
        values,
    )


def trigger_one(work_item_id: str, *, now: float | None = None, force_retry: bool = False) -> dict[str, Any]:
    current = now if now is not None else time.time()
    conn = db.get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        policy_row = conn.execute(
            "SELECT * FROM work_item_execution_policies WHERE work_item_id=?",
            (work_item_id,),
        ).fetchone()
        item_row = conn.execute("SELECT * FROM work_items WHERE id=?", (work_item_id,)).fetchone()
        if policy_row is None or item_row is None:
            conn.commit()
            return {"state": "missing"}
        policy = _row(policy_row)
        item = db._row_to_work_item(item_row)
        if policy["mode"] != "auto":
            _update_state(conn, work_item_id, state="manual")
            conn.commit()
            return get_policy(work_item_id, str(item["project_id"]))
        if str(item.get("status") or "") == "done":
            acceptance = conn.execute(
                "SELECT run_id FROM work_item_acceptances WHERE work_item_id=? AND project_id=?",
                (work_item_id, item["project_id"]),
            ).fetchone()
            _update_state(
                conn, work_item_id,
                state="accepted" if acceptance is not None else "completed_without_acceptance",
                blocker_code="" if acceptance is not None else "completed_without_acceptance",
                blocker_message="" if acceptance is not None else "任务已手工完成，但没有交付验收记录",
                last_run_id=str(acceptance["run_id"]) if acceptance is not None else None,
            )
            conn.commit()
            return get_policy(work_item_id, str(item["project_id"]))
        latest = conn.execute(
            "SELECT * FROM business_runs WHERE work_item_id=? AND owner_id=? AND deleted_at=0 "
            "AND client_request_id LIKE ? ORDER BY created_at DESC,id DESC LIMIT 1",
            (work_item_id, policy["execution_owner_id"], f"work-item-auto:{work_item_id}:v{policy['version']}:%"),
        ).fetchone()
        retry_of = None
        attempt = 1
        if latest is not None:
            latest_status = str(latest["status"])
            attempt = int(policy.get("last_attempt") or 0) or 1
            if latest_status in ACTIVE_RUN_STATUSES:
                _update_state(
                    conn, work_item_id, state="queued" if latest_status == "queued" else "running",
                    last_run_id=str(latest["id"]), last_attempt=attempt,
                )
                conn.commit()
                return get_policy(work_item_id, str(item["project_id"]))
            if latest_status in SUCCESS_RUN_STATUSES:
                verified_assets = int(conn.execute(
                    "SELECT COUNT(*) FROM business_assets WHERE run_id=? AND deleted_at=0 "
                    "AND storage_state='committed' AND validation_status='verified'",
                    (latest["id"],),
                ).fetchone()[0])
                if verified_assets:
                    _update_state(conn, work_item_id, state="awaiting_acceptance")
                    conn.commit()
                    return get_policy(work_item_id, str(item["project_id"]))
            if attempt >= int(policy["max_attempts"]):
                _update_state(
                    conn, work_item_id, state="failed", blocker_code="retry_exhausted",
                    blocker_message="自动执行已耗尽重试次数",
                )
                conn.commit()
                return get_policy(work_item_id, str(item["project_id"]))
            ready_at = float(latest["ended_at"] or latest["updated_at"] or current) + int(policy["retry_backoff_sec"])
            if not force_retry and current < ready_at:
                _update_state(
                    conn, work_item_id, state="waiting_retry", blocker_code="retry_backoff",
                    blocker_message=f"等待重试退避至 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ready_at))}",
                )
                conn.commit()
                return get_policy(work_item_id, str(item["project_id"]))
            retry_of = str(latest["id"])
            attempt += 1
        blocker_code, blocker_message = _gate(
            policy, item, current, retrying=retry_of is not None,
        )
        if blocker_code:
            _update_state(
                conn, work_item_id, state="blocked", blocker_code=blocker_code,
                blocker_message=blocker_message,
            )
            conn.commit()
            return get_policy(work_item_id, str(item["project_id"]))
        key = f"work-item-auto:{work_item_id}:v{policy['version']}:attempt:{attempt}"
        prompt = f"完成项目工作项：{item['title']}"
        if str(item.get("description") or "").strip():
            prompt += f"\n\n要求：\n{str(item['description']).strip()}"
        prompt += "\n\n请真实执行并生成可验收交付物；在产物被人工验收前不要把工作项标记为完成。"
        signature = {
            "work_item_id": work_item_id,
            "policy_version": policy["version"],
            "attempt": attempt,
            "retry_of": retry_of,
            "routing_mode": policy["routing_mode"],
            "target_device_id": policy["target_device_id"],
        }
        request_hash = hashlib.sha256(_json(signature).encode("utf-8")).hexdigest()
        session, _message, run, _duplicate = business_store.create_turn(
            actor_id=str(policy["execution_owner_id"]),
            owner_id=str(policy["execution_owner_id"]),
            project_id=str(item["project_id"]),
            session_id=None,
            session_title=str(item["title"])[:500],
            session_kind="projexec",
            session_space=None,
            user_text=prompt,
            client_request_id=key,
            request_hash=request_hash,
            run_fields={
                "work_item_id": work_item_id,
                "mode": "exec",
                "workspace": f"project:{item['project_id']}",
                "retry_of": retry_of,
                "model_ref": policy.get("model_ref"),
                "model_id": None,
                "model_snapshot": {},
                "permission_snapshot": {
                    "execution_source": "work_item_auto",
                    "preauthorized_permissions": policy["preauthorized_permissions"],
                    "timeout_sec": int(policy["timeout_sec"]),
                    "max_total_tokens": int(policy["max_total_tokens"]),
                },
                "target_device_id": (
                    str(policy["target_device_id"])
                    if policy["routing_mode"] == "specific" else ""
                ),
                "required_capabilities": policy["required_capabilities"],
                "request_snapshot": {
                    "work_item_id": work_item_id,
                    "work_item_auto_policy_version": int(policy["version"]),
                    "work_item_auto_attempt": attempt,
                    "loadout": {},
                    "refs": [{"name": item["title"], "kind": "todo", "itemId": work_item_id}],
                },
                "max_recoveries": 3,
            },
            connection=conn,
        )
        assignee = str(item.get("assignee") or "") or str(policy["execution_owner_id"])
        conn.execute(
            "UPDATE work_items SET status='doing',assignee=?,updated_at=? WHERE id=?",
            (assignee, current, work_item_id),
        )
        conn.execute(
            "INSERT INTO work_item_activity (id,project_id,work_item_id,actor,kind,detail,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                db.new_uuid(), item["project_id"], work_item_id, "AgentMate",
                "auto_execution_queued", f"run={run['id']}; policy_version={policy['version']}; attempt={attempt}",
                current,
            ),
        )
        _update_state(
            conn, work_item_id, state="queued", last_run_id=str(run["id"]),
            last_trigger_key=key, last_attempt=attempt,
        )
        conn.commit()
        return get_policy(work_item_id, str(item["project_id"]))
    except Exception:
        conn.rollback()
        raise


def scan_once(now: float | None = None) -> int:
    current = now if now is not None else time.time()
    ids = [
        str(row["work_item_id"])
        for row in db.get_conn().execute(
            "SELECT work_item_id FROM work_item_execution_policies WHERE mode='auto' "
            "ORDER BY updated_at,work_item_id LIMIT 100"
        ).fetchall()
    ]
    for work_item_id in ids:
        try:
            trigger_one(work_item_id, now=current)
        except Exception:  # noqa: BLE001 - one policy must not stop the scheduler
            log.exception("failed to evaluate WorkItem auto policy %s", work_item_id)
    return len(ids)


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(scan_once)
        except Exception:  # noqa: BLE001 - recurring scanner must survive transient failures
            log.exception("WorkItem auto scheduler scan failed")
        await asyncio.sleep(POLL_SECONDS)
