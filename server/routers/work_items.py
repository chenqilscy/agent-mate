"""团队计划/任务 work_items（WB-081）。

项目级看板/任务，团队共享。access-gated（owner OR 成员）；Viewer 只读、Member+ 可写。
本地 App 的 work_items 目前是本地独有；本地⇄Server 双向同步为后续（见 WB-081 处理记录）。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from math import isfinite
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

import business_store
import db
from auth import CurrentAccount
from models import Account, Role, can_write
from project_health_service import observe_project_health

router = APIRouter(prefix="/api", tags=["work-items"])

_STATUSES = {"todo", "doing", "paused", "review", "done"}
_PRIORITIES = {"", "low", "medium", "high", "urgent"}
# 记入活动流的关键字段（值变化时逐条留痕，来自真实操作）。
_TRACKED = ("status", "assignee", "priority", "due_date", "milestone_id", "sprint_id")
_ACTION_REASON_RANK = {
    "overdue": 0,
    "due_today": 1,
    "blocked": 2,
    "in_progress": 3,
    "awaiting_acceptance": 4,
    "starts_today": 5,
    "ready": 6,
    "urgent": 7,
}


def _access(project_id: str, account: Account) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_write(project_id: str, account: Account) -> None:
    if not can_write(_access(project_id, account)):
        raise HTTPException(403, "Viewer is read-only")
    if db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")


# 负责人强映射（WB-112c-B）：assignee 权威值 = 成员 account_id；写时把「名字/id」归一到 id，
# 读时解析 assignee_name（解析不到用原值兜底，不丢历史文本）。
def _members_maps(project_id: str) -> tuple[dict, dict]:
    mem = db.list_project_members(project_id)
    by_id = {m["account_id"]: m.get("name", "") for m in mem}
    by_name = {(m.get("name") or "").lower(): m["account_id"] for m in mem if m.get("name")}
    return by_id, by_name


def _norm_assignee(raw: str, by_id: dict, by_name: dict) -> str:
    a = (raw or "").strip()
    if not a or a in by_id:
        return a
    normalized = by_name.get(a.lower())
    if normalized:
        return normalized
    raise HTTPException(400, "assignee must be an existing project member")


def _validate_date(value: str, name: str) -> None:
    if not value:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, f"invalid {name}") from exc


def _validate_scalar(changes: dict, current: dict | None = None) -> None:
    if "title" in changes:
        changes["title"] = str(changes["title"] or "").strip()
        if not changes["title"]:
            raise HTTPException(400, "empty work item title")
    for key in ("due_date", "start_date"):
        if key in changes:
            changes[key] = str(changes[key] or "").strip()
            _validate_date(changes[key], key)
    start = str(changes.get("start_date", (current or {}).get("start_date", "")) or "")
    due = str(changes.get("due_date", (current or {}).get("due_date", "")) or "")
    if start and due and date.fromisoformat(due) < date.fromisoformat(start):
        raise HTTPException(400, "due_date must be on or after start_date")
    for key in ("estimate_h", "spent_h"):
        if key in changes:
            value = float(changes[key])
            if not isfinite(value) or value < 0 or value > 1_000_000:
                raise HTTPException(400, f"{key} must be between 0 and 1000000")
            changes[key] = value
    if "labels" in changes:
        raw = changes.get("labels") or []
        if len(raw) > 50:
            raise HTTPException(400, "too many labels")
        changes["labels"] = list(dict.fromkeys(str(value).strip()[:80] for value in raw if str(value).strip()))


def _decorate(item: dict, by_id: dict) -> dict:
    a = item.get("assignee") or ""
    item["assignee_name"] = by_id.get(a, a)
    # Server stores immutable assets separately; the App WorkItem contract still
    # requires a list so opening a Server-created task never dereferences undefined.
    item["attachments"] = []
    item["delivery_accepted"] = db.get_work_item_acceptance(item["id"]) is not None
    return item


def _action_signals(item: dict, as_of: date) -> list[str]:
    """Return explainable reasons why an unfinished item belongs in today's inbox."""
    if item.get("status") == "done":
        return []
    today = as_of.isoformat()
    due = str(item.get("due_date") or "")
    start = str(item.get("start_date") or "")
    status = str(item.get("status") or "")
    signals: list[str] = []
    if due and due < today:
        signals.append("overdue")
    elif due == today:
        signals.append("due_today")
    if status == "paused":
        signals.append("blocked")
    elif status == "doing":
        signals.append("in_progress")
    elif status == "review":
        signals.append("awaiting_acceptance")
    if start == today:
        signals.append("starts_today")
    elif start and start < today and status == "todo":
        signals.append("ready")
    if item.get("priority") == "urgent" and (not start or start <= today):
        signals.append("urgent")
    return sorted(set(signals), key=lambda value: _ACTION_REASON_RANK[value])


def _action_sort_key(item: dict) -> tuple:
    signals = item.get("action_signals") or []
    priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "": 4}
    return (
        _ACTION_REASON_RANK.get(str(signals[0]) if signals else "", 99),
        priority_rank.get(str(item.get("priority") or ""), 4),
        str(item.get("due_date") or "9999-12-31"),
        str((item.get("project") or {}).get("name") or "").casefold(),
        str(item.get("title") or "").casefold(),
        str(item.get("id") or ""),
    )


@router.get("/work-items/action-items")
def personal_action_items(
    as_of: str = Query(default=""), account: Account = CurrentAccount,
) -> dict:
    """Current account's actionable WorkItems across every authorized project."""
    try:
        effective_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as exc:
        raise HTTPException(400, "invalid as_of") from exc

    assigned: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    backlog_count = 0
    reason_counts = {name: 0 for name in _ACTION_REASON_RANK}
    for project, role in db.list_projects_for(account.id):
        work_items = db.list_work_items(project.id)
        by_id, _ = _members_maps(project.id)
        critical = _critical_path_ids(work_items)
        for raw in work_items:
            if raw.get("status") == "done":
                continue
            assignee = str(raw.get("assignee") or "")
            if assignee not in {"", account.id}:
                continue
            signals = _action_signals(raw, effective_date)
            if not signals:
                if assignee == account.id:
                    backlog_count += 1
                continue
            item = {
                **_decorate(dict(raw), by_id),
                "critical_path": raw["id"] in critical,
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "role": role.value,
                },
                "action_signals": signals,
                "action_reason": signals[0],
            }
            for signal in signals:
                reason_counts[signal] += 1
            (unassigned if not assignee else assigned).append(item)

    assigned.sort(key=_action_sort_key)
    unassigned.sort(key=_action_sort_key)
    return {
        "as_of": effective_date.isoformat(),
        "computed_at": time.time(),
        "source": "server",
        "items": assigned,
        "unassigned": unassigned,
        "summary": {
            "assigned": len(assigned),
            "unassigned": len(unassigned),
            "backlog": backlog_count,
            **reason_counts,
        },
    }


def _sync_linked_risk(
    project_id: str, work_item_id: str, status: str, account: Account,
    *, run_id: str = "",
) -> None:
    if status not in {"doing", "paused", "review", "done"}:
        return
    for record in db.list_project_governance(project_id):
        if (
            record.get("record_type") != "risk"
            or record.get("status") == "closed"
            or record.get("work_item_id") != work_item_id
        ):
            continue
        changes = {"status": "mitigating"}
        if run_id:
            changes["run_id"] = run_id
        db.update_project_governance(record["id"], **changes)
        db.log_project_governance_activity(
            project_id=project_id, record_id=record["id"], actor_id=account.id,
            kind="action_task_status", detail=f"{work_item_id}:{status}",
        )


def _sanitize_refs(
    project_id: str, self_id: str | None, changes: dict,
    current_custom_fields: dict | None = None,
) -> None:
    """把 parent_id/milestone_id 归一到「同项目存在的行」，否则置空 —— 防跨项目引用（删除时
    会跨租户级联）与指向不存在/自身导致任务从所有视图消失的幽灵父任务（WB-157）。"""
    if "parent_id" in changes:
        pid = (changes.get("parent_id") or "").strip()
        p = db.get_work_item(pid) if pid and pid != self_id else None
        changes["parent_id"] = pid if (p and p["project_id"] == project_id) else ""
        if self_id and changes["parent_id"]:
            parents = {
                item["id"]: str(item.get("parent_id") or "")
                for item in db.list_work_items(project_id)
            }
            parents[self_id] = changes["parent_id"]
            cursor = changes["parent_id"]
            seen: set[str] = set()
            while cursor:
                if cursor == self_id or cursor in seen:
                    raise HTTPException(409, "work item parent cycle")
                seen.add(cursor)
                cursor = parents.get(cursor, "")
    if "milestone_id" in changes:
        mid = (changes.get("milestone_id") or "").strip()
        m = db.get_milestone(mid) if mid else None
        changes["milestone_id"] = mid if (m and m["project_id"] == project_id) else ""
    if "sprint_id" in changes:
        sid = (changes.get("sprint_id") or "").strip()
        sprint = db.get_sprint(sid) if sid else None
        changes["sprint_id"] = sid if (sprint and sprint["project_id"] == project_id) else ""
    if "dependency_ids" in changes:
        deps: list[str] = []
        for raw in changes.get("dependency_ids") or []:
            dep_id = str(raw).strip()
            dep = db.get_work_item(dep_id) if dep_id and dep_id != self_id else None
            if dep and dep["project_id"] == project_id and dep_id not in deps:
                deps.append(dep_id)
        changes["dependency_ids"] = deps
        if self_id:
            graph = {item["id"]: list(item.get("dependency_ids") or []) for item in db.list_work_items(project_id)}
            graph[self_id] = deps
            def reaches_self(node: str, seen: set[str]) -> bool:
                if node == self_id:
                    return True
                if node in seen:
                    return False
                return any(reaches_self(child, seen | {node}) for child in graph.get(node, []))
            if any(reaches_self(dep, set()) for dep in deps):
                raise HTTPException(409, "work item dependency cycle")
    if "custom_fields" in changes:
        raw = changes.get("custom_fields")
        definitions = {item["id"]: item for item in db.list_project_custom_fields(project_id)}
        values = raw if isinstance(raw, dict) else {}
        if len(values) > 50:
            raise HTTPException(400, "too many custom field values")
        unknown = [str(key) for key in values if str(key) not in definitions]
        if unknown:
            raise HTTPException(400, f"unknown custom field: {unknown[0]}")
        clean: dict[str, str | int | float | bool] = {}
        for raw_key, value in values.items():
            key = str(raw_key)
            definition = definitions[key]
            kind = definition["field_type"]
            valid = (
                (kind in {"text", "date", "select"} and isinstance(value, str))
                or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
                or (kind == "boolean" and isinstance(value, bool))
            )
            if not valid:
                raise HTTPException(400, f"invalid value for custom field {definition['name']}")
            if kind == "date":
                _validate_date(value, f"custom field {definition['name']}")
            if kind == "select" and value not in definition["options"]:
                raise HTTPException(400, f"invalid option for custom field {definition['name']}")
            clean[key] = value
        merged = dict((current_custom_fields or {}))
        merged.update(clean)
        for key, definition in definitions.items():
            if definition["required"] and (key not in merged or merged[key] in ("", None)):
                raise HTTPException(400, f"required custom field missing: {definition['name']}")
        changes["custom_fields"] = clean


def _critical_path_ids(items: list[dict]) -> set[str]:
    """Return one deterministic longest dependency chain using estimate hours as duration."""
    by_id = {item["id"]: item for item in items}
    memo: dict[str, tuple[float, list[str]]] = {}
    def visit(item_id: str, visiting: set[str]) -> tuple[float, list[str]]:
        if item_id in memo:
            return memo[item_id]
        if item_id in visiting:
            return (0.0, [])
        item = by_id[item_id]
        candidates = [visit(dep, visiting | {item_id}) for dep in item.get("dependency_ids", []) if dep in by_id]
        previous = max(candidates, key=lambda value: (value[0], value[1]), default=(0.0, []))
        result = (previous[0] + max(1.0, float(item.get("estimate_h") or 0)), [*previous[1], item_id])
        memo[item_id] = result
        return result
    if not items:
        return set()
    return set(max((visit(item_id, set()) for item_id in sorted(by_id)), key=lambda value: (value[0], value[1]))[1])


@router.get("/projects/{project_id}/work-items")
def list_items(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    by_id, _ = _members_maps(project_id)
    items = db.list_work_items(project_id)
    critical = _critical_path_ids(items)
    return {"items": [{**_decorate(it, by_id), "critical_path": it["id"] in critical} for it in items]}


def _run_artifact_view(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        **asset,
        "path": str(asset.get("object_ref") or ""),
        "preview_path": None,
        "is_primary": False,
        "display_order": 0,
        "verification": {
            "exists": asset.get("storage_state") == "committed",
            "hash_matches": asset.get("validation_status") == "verified",
        },
    }


@router.get("/projects/{project_id}/work-items/{wid}/delivery")
def item_delivery(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    role = _access(project_id, account)
    item = db.get_work_item(wid)
    if not item or item["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    runs, _ = business_store.list_scoped(
        "business_runs", account_id=account.id, project_id=project_id,
        parent=("work_item_id", wid), limit=100,
    )
    launches: list[dict[str, Any]] = []
    values: list[dict[str, Any]] = []
    for run in runs:
        assets, _ = business_store.list_scoped(
            "business_assets", account_id=account.id, project_id=project_id,
            parent=("run_id", str(run["id"])), limit=500,
        )
        status = str(run.get("status") or "queued")
        launches.append({
            "id": run["id"], "work_item_id": wid, "owner_id": run["owner_id"],
            "idempotency_key": run.get("client_request_id") or "",
            "session_id": run.get("session_id"), "run_id": run["id"],
            "status": "running" if status in {"running", "planning", "waiting_user"}
            else "completed" if status in {"completed", "succeeded"}
            else "cancelled" if status == "cancelled"
            else "failed" if status == "failed" else "queued",
            "error_code": run.get("error_code"), "error_message": run.get("error_message"),
            "created_at": run.get("created_at") or 0, "updated_at": run.get("updated_at") or 0,
            "finished_at": run.get("ended_at"),
        })
        values.append({**run, "artifacts": [_run_artifact_view(asset) for asset in assets]})
    by_id, _ = _members_maps(project_id)
    return {
        "work_item": _decorate(item, by_id),
        "can_write": can_write(role) and not db.project_is_archived(project_id),
        "launches": launches,
        "runs": values,
    }


class ExecuteBody(BaseModel):
    target_device_id: str = Field(min_length=8, max_length=200)
    local_input_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    model_ref: str | None = Field(default=None, max_length=200)


@router.post("/projects/{project_id}/work-items/{wid}/execute")
def execute_item(
    project_id: str, wid: str, body: ExecuteBody,
    account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    _require_write(project_id, account)
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(400, "Idempotency-Key is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", key):
        raise HTTPException(400, "invalid Idempotency-Key")
    item = db.get_work_item(wid)
    if not item or item["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    if item["status"] == "done":
        raise HTTPException(409, "completed work item cannot be executed again")
    target = db.get_conn().execute(
        "SELECT owner_id,status FROM agent_devices WHERE id=?", (body.target_device_id,),
    ).fetchone()
    if target is None or str(target["owner_id"]) != account.id or str(target["status"]) != "active":
        raise HTTPException(400, "target device is not an active device owned by this account")
    prompt = f"完成项目工作项：{item['title']}"
    if str(item.get("description") or "").strip():
        prompt += f"\n\n要求：\n{str(item['description']).strip()}"
    prompt += "\n\n请真实执行并生成可验收交付物；在产物被人工验收前不要把工作项标记为完成。"
    request_snapshot = {
        "loadout": {},
        "refs": [{"name": item["title"], "kind": "todo", "itemId": wid}],
        "local_input_key": body.local_input_key,
        "work_item_id": wid,
    }
    payload = {
        "project_id": project_id, "work_item_id": wid, "prompt": prompt,
        "target_device_id": body.target_device_id, "local_input_key": body.local_input_key,
        "model_ref": body.model_ref,
    }
    request_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    conn = db.get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        session, message, run, duplicate = business_store.create_turn(
            actor_id=account.id, owner_id=account.id, project_id=project_id,
            session_id=None, session_title=str(item["title"])[:500],
            session_kind="projexec", session_space=None, user_text=prompt,
            client_request_id=key, request_hash=request_hash,
            run_fields={
                "work_item_id": wid, "mode": "exec", "workspace": f"project:{project_id}",
                "retry_of": None, "model_ref": body.model_ref, "model_id": None,
                "model_snapshot": {},
                # Clicking "交给 Agent 执行" is an explicit user grant for this
                # project sandbox.  Background Runs still fail closed for every
                # other restricted authority (process/host/network/connectors).
                "permission_snapshot": {
                    "execution_source": "background",
                    "preauthorized_permissions": ["workspace.write"],
                },
                "target_device_id": body.target_device_id,
                "required_capabilities": ["run_events_v1", "llm.chat", "agent.tools"],
                "request_snapshot": request_snapshot, "max_recoveries": 3,
            },
            connection=conn,
        )
        if not duplicate:
            now = time.time()
            conn.execute("UPDATE work_items SET status='doing',updated_at=? WHERE id=?", (now, wid))
            conn.execute(
                "INSERT INTO work_item_activity (id,project_id,work_item_id,actor,kind,detail,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (db.new_uuid(), project_id, wid, account.name, "execution_started", f"run={run['id']}", now),
            )
        conn.commit()
    except business_store.IdempotencyConflict as exc:
        conn.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    return {"session": session, "user_message": message, "run": run, "duplicate": duplicate}


class CreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    status: str = "todo"
    source: str = Field(default="手动", max_length=80)
    assignee: str = ""
    description: str = Field(default="", max_length=20000)
    priority: str = ""            # '' | low | medium | high | urgent
    due_date: str = ""            # YYYY-MM-DD
    start_date: str = ""
    labels: list[str] = Field(default_factory=list, max_length=50)
    parent_id: str = ""           # 自引用 → 子任务
    milestone_id: str = ""
    estimate_h: float = 0.0       # 工时预估/投入（WB-117）
    spent_h: float = 0.0
    custom_fields: dict[str, str | int | float | bool] = Field(default_factory=dict)
    dependency_ids: list[str] = Field(default_factory=list, max_length=100)
    sprint_id: str = ""


@router.post("/projects/{project_id}/work-items")
def create_item(project_id: str, body: CreateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    if body.status not in _STATUSES:
        raise HTTPException(400, "invalid status")
    if body.priority not in _PRIORITIES:
        raise HTTPException(400, "invalid priority")
    by_id, by_name = _members_maps(project_id)
    values = body.model_dump()
    _validate_scalar(values)
    refs = {"parent_id": body.parent_id, "milestone_id": body.milestone_id,
            "custom_fields": body.custom_fields, "dependency_ids": body.dependency_ids,
            "sprint_id": body.sprint_id}
    _sanitize_refs(project_id, None, refs)
    observe_project_health(project_id, actor_name=account.name)
    item = db.create_work_item(
        project_id=project_id, title=values["title"], status=body.status,
        source=body.source, assignee=_norm_assignee(body.assignee, by_id, by_name),
        description=body.description,
        priority=body.priority, due_date=values["due_date"], start_date=values["start_date"],
        labels=values["labels"], parent_id=refs["parent_id"], milestone_id=refs["milestone_id"],
        estimate_h=values["estimate_h"], spent_h=values["spent_h"],
        custom_fields=refs["custom_fields"], dependency_ids=refs["dependency_ids"], sprint_id=refs["sprint_id"],
    )
    db.log_work_item_activity(project_id=project_id, work_item_id=item["id"],
                              actor=account.name, kind="created", detail=item["title"])
    observe_project_health(project_id, actor_name=account.name)
    return _decorate(item, by_id)


class UpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    status: str | None = None
    source: str | None = Field(default=None, max_length=80)
    assignee: str | None = None
    description: str | None = Field(default=None, max_length=20000)
    sort: int | None = None
    priority: str | None = None
    due_date: str | None = None
    start_date: str | None = None
    labels: list[str] | None = Field(default=None, max_length=50)
    parent_id: str | None = None
    milestone_id: str | None = None
    estimate_h: float | None = None    # 工时预估/投入（WB-116）
    spent_h: float | None = None
    custom_fields: dict[str, str | int | float | bool] | None = None
    dependency_ids: list[str] | None = Field(default=None, max_length=100)
    sprint_id: str | None = None


@router.patch("/projects/{project_id}/work-items/{wid}")
def update_item(project_id: str, wid: str, body: UpdateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    if body.status is not None and body.status not in _STATUSES:
        raise HTTPException(400, "invalid status")
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "done" and it["status"] == "review":
        raise HTTPException(409, "review work item requires delivery acceptance")
    if "priority" in changes and changes["priority"] not in _PRIORITIES:
        raise HTTPException(400, "invalid priority")
    _validate_scalar(changes, it)
    _sanitize_refs(project_id, wid, changes, it.get("custom_fields") or {})
    by_id, by_name = _members_maps(project_id)
    if "assignee" in changes:
        changes["assignee"] = _norm_assignee(changes["assignee"], by_id, by_name)
    observe_project_health(project_id, actor_name=account.name)
    updated = db.update_work_item(wid, **changes)
    if not updated:
        raise HTTPException(404, "work item not found")
    # 活动流：关键字段变化逐条留痕（assignee 用成员名，别记 account_id）。
    for k in _TRACKED:
        if k in changes and str(changes[k]) != str(it.get(k, "")):
            old, new = it.get(k, ""), changes[k]
            if k == "assignee":
                old, new = by_id.get(old, old) or "未指派", by_id.get(new, new) or "未指派"
            db.log_work_item_activity(project_id=project_id, work_item_id=wid, actor=account.name,
                                      kind=k, detail=f"{old}→{new}")
    if "status" in changes:
        _sync_linked_risk(project_id, wid, str(changes["status"]), account)
    observe_project_health(project_id, actor_name=account.name)
    return _decorate(updated, by_id)


class AcceptBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=120)
    artifact_count: int = Field(ge=1, le=10000)


@router.post("/projects/{project_id}/work-items/{wid}/accept")
def accept_item(project_id: str, wid: str, body: AcceptBody, account: Account = CurrentAccount) -> dict:
    """Close only after the authoritative Server Run has verified immutable assets."""
    _require_write(project_id, account)
    observe_project_health(project_id, actor_name=account.name)
    try:
        run = business_store.get_record("business_runs", body.run_id)
        if run is not None:
            updated, assets, _replayed = db.accept_server_work_item_delivery(
                project_id=project_id, work_item_id=wid, run_id=body.run_id,
                actor_id=account.id, actor_name=account.name,
                expected_artifact_count=body.artifact_count,
            )
        else:
            # Compatibility for an in-flight legacy Local Agent launch during cutover.
            updated, _replayed = db.accept_work_item_delivery(
                project_id=project_id, work_item_id=wid, run_id=body.run_id,
                artifact_count=body.artifact_count, actor_id=account.id, actor_name=account.name,
            )
    except KeyError as exc:
        raise HTTPException(404, "work item not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    _sync_linked_risk(project_id, wid, "done", account, run_id=body.run_id)
    observe_project_health(project_id, actor_name=account.name)
    return _decorate(updated, _members_maps(project_id)[0])


@router.delete("/projects/{project_id}/work-items/{wid}")
def delete_item(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    observe_project_health(project_id, actor_name=account.name)
    db.delete_work_item(wid)
    observe_project_health(project_id, actor_name=account.name)
    return {"ok": True}


@router.get("/projects/{project_id}/work-items/{wid}/activity")
def item_activity(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_work_item_activity(project_id, wid)}


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_work_item_activity(project_id)}
