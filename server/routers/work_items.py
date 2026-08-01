"""团队计划/任务 work_items（WB-081）。

项目级看板/任务，团队共享。access-gated（owner OR 成员）；Viewer 只读、Member+ 可写。
本地 App 的 work_items 目前是本地独有；本地⇄Server 双向同步为后续（见 WB-081 处理记录）。
"""
from __future__ import annotations

from datetime import date
from math import isfinite

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account, Role, can_write

router = APIRouter(prefix="/api", tags=["work-items"])

_STATUSES = {"todo", "doing", "paused", "review", "done"}
_PRIORITIES = {"", "low", "medium", "high", "urgent"}
# 记入活动流的关键字段（值变化时逐条留痕，来自真实操作）。
_TRACKED = ("status", "assignee", "priority", "due_date", "milestone_id", "sprint_id")


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
    return item


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
    return _decorate(updated, by_id)


class AcceptBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=120)
    artifact_count: int = Field(ge=1, le=10000)


@router.post("/projects/{project_id}/work-items/{wid}/accept")
def accept_item(project_id: str, wid: str, body: AcceptBody, account: Account = CurrentAccount) -> dict:
    """Close only after the local execution plane attests verified artifacts."""
    _require_write(project_id, account)
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    if it["status"] != "review":
        raise HTTPException(409, "work item is not awaiting acceptance")
    updated = db.update_work_item(wid, status="done")
    assert updated is not None
    db.log_work_item_activity(
        project_id=project_id, work_item_id=wid, actor=account.name,
        kind="accepted", detail=f"run={body.run_id}; artifacts={body.artifact_count}",
    )
    return _decorate(updated, _members_maps(project_id)[0])


@router.delete("/projects/{project_id}/work-items/{wid}")
def delete_item(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    db.delete_work_item(wid)
    return {"ok": True}


@router.get("/projects/{project_id}/work-items/{wid}/activity")
def item_activity(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_work_item_activity(project_id, wid)}


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_work_item_activity(project_id)}
