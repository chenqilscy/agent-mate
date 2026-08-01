"""Work items — kanban / task list (§11 阶段 B). 计划 and 任务 share this source."""
from __future__ import annotations

import asyncio
import time
import uuid

from datetime import date
from math import isfinite
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import server_client
from agent import work_item_runner
from auth.deps import current_user
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api", tags=["work_items"])

STATUSES = {"todo", "doing", "paused", "review", "done"}
PRIORITIES = {"", "low", "medium", "high", "urgent"}
MAX_ATTACHMENTS = 20
MAX_LABELS = 20


def _clean_labels(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for s in raw[:MAX_LABELS]:
        t = str(s).strip()[:40]
        if t and t not in out:
            out.append(t)
    return out


def _clean_attachments(raw: Any) -> list[dict]:
    """只保留 {name, kind, path} 形状的引用，防止塞进任意 JSON。不复制文件、只存引用。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for a in raw[:MAX_ATTACHMENTS]:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "")).strip()[:200]
        if not name:
            continue
        kind = a.get("kind") if a.get("kind") in ("local", "asset") else "local"
        path = a.get("path")
        out.append({"name": name, "kind": kind, "path": str(path)[:500] if path else None})
    return out


def _validate_local_fields(changes: dict, current=None) -> None:
    """Local projects enforce the same scalar PM rules as the Server authority."""
    if "title" in changes:
        changes["title"] = str(changes["title"] or "").strip()
        if not changes["title"]:
            raise HTTPException(400, "empty work item title")
    for key in ("due_date", "start_date"):
        if key not in changes:
            continue
        value = str(changes[key] or "").strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(400, f"invalid {key}") from exc
        changes[key] = value or None
    current_start = getattr(current, "start_date", None) if current else None
    current_due = getattr(current, "due_date", None) if current else None
    start = changes.get("start_date", current_start)
    due = changes.get("due_date", current_due)
    if start and due and date.fromisoformat(due) < date.fromisoformat(start):
        raise HTTPException(400, "due_date must be on or after start_date")
    for key in ("estimate_h", "spent_h"):
        if key in changes and changes[key] is not None:
            value = float(changes[key])
            if not isfinite(value) or value < 0 or value > 1_000_000:
                raise HTTPException(400, f"{key} must be between 0 and 1000000")
            changes[key] = value
    if "labels" in changes and changes["labels"] is not None:
        changes["labels"] = _clean_labels(changes["labels"])


def _sanitize_local_refs(project_id: str, self_id: str | None, changes: dict) -> None:
    items = db.list_work_items(project_id)
    by_id = {item.id: item for item in items}
    if "parent_id" in changes:
        parent_id = str(changes.get("parent_id") or "").strip()
        changes["parent_id"] = parent_id if parent_id in by_id and parent_id != self_id else ""
        if self_id and changes["parent_id"]:
            parents = {item.id: item.parent_id for item in items}
            parents[self_id] = changes["parent_id"]
            cursor = changes["parent_id"]
            seen: set[str] = set()
            while cursor:
                if cursor == self_id or cursor in seen:
                    raise HTTPException(409, "work item parent cycle")
                seen.add(cursor)
                cursor = parents.get(cursor, "")
    if "milestone_id" in changes:
        milestone_id = str(changes.get("milestone_id") or "").strip()
        milestone = db.get_milestone(milestone_id) if milestone_id else None
        changes["milestone_id"] = (
            milestone_id if milestone and milestone["project_id"] == project_id else ""
        )
    if "sprint_id" in changes:
        # Local storage has no Sprint authority; accepting an arbitrary ID would create a ghost reference.
        changes["sprint_id"] = ""
    if "dependency_ids" in changes:
        dependencies: list[str] = []
        for raw in changes.get("dependency_ids") or []:
            dependency_id = str(raw).strip()
            if dependency_id in by_id and dependency_id != self_id and dependency_id not in dependencies:
                dependencies.append(dependency_id)
        if len(dependencies) > 100:
            raise HTTPException(400, "too many dependencies")
        changes["dependency_ids"] = dependencies
        if self_id:
            graph = {item.id: list(item.dependency_ids) for item in items}
            graph[self_id] = dependencies

            def reaches_self(node: str, seen: set[str]) -> bool:
                if node == self_id:
                    return True
                if node in seen:
                    return False
                return any(reaches_self(child, seen | {node}) for child in graph.get(node, []))

            if any(reaches_self(dependency, set()) for dependency in dependencies):
                raise HTTPException(409, "work item dependency cycle")


class CreateWorkItemBody(BaseModel):
    project_id: str
    title: str
    status: str = "todo"
    source: str = "手动"
    description: str = ""
    due_date: str | None = None
    attachments: list[dict] = []
    priority: str = ""
    start_date: str | None = None
    labels: list[str] = []
    parent_id: str = ""
    milestone_id: str = ""
    estimate_h: float = 0.0
    spent_h: float = 0.0
    custom_fields: dict[str, str | int | float | bool] = {}
    dependency_ids: list[str] = []
    sprint_id: str = ""


class UpdateWorkItemBody(BaseModel):
    title: str | None = None
    status: str | None = None
    description: str | None = None
    due_date: str | None = None
    attachments: list[dict] | None = None
    priority: str | None = None
    start_date: str | None = None
    labels: list[str] | None = None
    parent_id: str | None = None
    milestone_id: str | None = None
    estimate_h: float | None = None
    spent_h: float | None = None
    custom_fields: dict[str, str | int | float | bool] | None = None
    dependency_ids: list[str] | None = None
    sprint_id: str | None = None


class ExecuteWorkItemBody(BaseModel):
    idempotency_key: str | None = None
    model: str | None = None


class AcceptWorkItemDeliveryBody(BaseModel):
    run_id: str


def _ago(ts: float) -> str:
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _assignee_name(assignee: str, user) -> str:
    """负责人显示名（WB-112c-B）：assignee 权威值 = account_id → 从 users 解析真名；
    解析不到（历史自由文本 / 尚未镜像）用原值兜底。"""
    a = (assignee or "").strip()
    if not a:
        return ""
    if a == user.id:
        return user.name
    u = db.get_user(a)
    return u.name if u else a


def _view(wi, user) -> dict:
    d = wi.to_dict()
    d["ago"] = _ago(wi.created_at)
    d["assignee_name"] = _assignee_name(wi.assignee, user)
    return d


# ---- Server 代理（WB-091）：server-origin 项目的 work_items 走 Server 权威（团队共享）----
# 读时把 Server 结果镜像进本地（离线兜底 + 让 update/delete 能按 id 定位 project）；
# 写时代理到 Server 再刷新镜像。Server 不可达 → 回退纯本地（离线优先，铁律 6 回退）。

def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _server_token(project_id: str, authorization: str) -> str:
    """该项目是否应走 Server 代理：server-origin 镜像项目 + 已接 Server + 请求带 token → 返回 bearer，否则 ""。"""
    if not server_client.server_enabled():
        return ""
    tok = _bearer(authorization)
    if not tok:
        return ""
    proj = db.get_project(project_id)
    if not proj or getattr(proj, "origin", "local") != "server":
        return ""
    return tok


def _server_write_token(project_id: str, authorization: str) -> str:
    """Server-origin writes must never fall through to the local mirror."""
    proj = db.get_project(project_id)
    if not proj or getattr(proj, "origin", "local") != "server":
        return ""
    if not server_client.server_enabled():
        raise HTTPException(503, "Server 未连接，Server 项目不能在本地写入")
    tok = _bearer(authorization)
    if not tok:
        raise HTTPException(401, "Server 项目写入需要登录凭据")
    return tok


def _server_view(it: dict) -> dict:
    """Server work_item → 前端期望的视图形状。
    专业 PM 字段（priority/start_date/labels/parent_id/milestone_id/due_date）随 Server 透传；
    owner_id/attachments 是本地专有、Server 不带，补默认空。"""
    ca = it.get("created_at") or 0
    labels = it.get("labels") or []
    return {
        "id": it.get("id"), "project_id": it.get("project_id"), "owner_id": "",
        "title": it.get("title", ""), "status": it.get("status", "todo"),
        "source": it.get("source", "手动"), "assignee": it.get("assignee", ""),
        "description": it.get("description", ""), "due_date": it.get("due_date") or None,
        "attachments": [],
        "priority": it.get("priority", ""), "start_date": it.get("start_date") or None,
        "labels": labels if isinstance(labels, list) else [],
        "parent_id": it.get("parent_id", ""), "milestone_id": it.get("milestone_id", ""),
        "estimate_h": float(it.get("estimate_h") or 0), "spent_h": float(it.get("spent_h") or 0),
        "custom_fields": it.get("custom_fields") if isinstance(it.get("custom_fields"), dict) else {},
        "dependency_ids": it.get("dependency_ids") if isinstance(it.get("dependency_ids"), list) else [],
        "sprint_id": it.get("sprint_id", ""), "critical_path": bool(it.get("critical_path", False)),
        "created_at": ca, "updated_at": it.get("updated_at") or ca,
        # Server 已按成员名解析 assignee_name（WB-112c-B）；缺失时用原值兜底。
        "ago": _ago(ca), "assignee_name": it.get("assignee_name") or (it.get("assignee", "") or ""),
    }


def _require_project_write(project_id: str, user_id: str) -> None:
    """Members (Owner/Admin/Member) may write a project's items; Viewer is read-only;
    non-members 404 (M7 C2)."""
    role = db.project_access_role(project_id, user_id)
    if role is None:
        raise HTTPException(404, "project not found")
    if role == Role.VIEWER:
        raise HTTPException(403, "只读成员不能修改任务")


@router.get("/work-items")
def list_items(project: str, authorization: str = Header(default="")) -> dict:
    user = current_user()
    # Any member (incl. Viewer) can see a project's items (M7 C2).
    if not db.get_project_for(project, user.id):
        raise HTTPException(404, "project not found")
    tok = _server_token(project, authorization)
    if tok:
        items = server_client.list_work_items(tok, project)  # None = Server 不可达
        if items is not None:
            db.mirror_server_work_items(project, items)       # 刷新本地镜像
            # 增量合并可能保留本地离线分叉；读取合并后的镜像，不能再用远端数组覆盖视图。
            return {"items": [_view(wi, user) for wi in db.list_work_items(project)]}
    return {"items": [_view(wi, user) for wi in db.list_work_items(project)]}


@router.post("/work-items")
def create_item(body: CreateWorkItemBody, authorization: str = Header(default="")) -> dict:
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "empty title")
    status = body.status if body.status in STATUSES else "todo"
    priority = body.priority if body.priority in PRIORITIES else ""
    labels = _clean_labels(body.labels)
    user = current_user()
    _require_project_write(body.project_id, user.id)
    tok = _server_write_token(body.project_id, authorization)
    if tok:
        created = server_client.create_work_item(
            tok, body.project_id,
            {"title": title, "status": status, "source": body.source,
             "description": (body.description or "").strip(),
             "priority": priority, "due_date": body.due_date or "",
             "start_date": body.start_date or "", "labels": labels,
             "parent_id": body.parent_id or "", "milestone_id": body.milestone_id or "",
             "estimate_h": body.estimate_h or 0, "spent_h": body.spent_h or 0,
             "custom_fields": body.custom_fields, "dependency_ids": body.dependency_ids,
             "sprint_id": body.sprint_id or ""},
        )
        if created:
            items = server_client.list_work_items(tok, body.project_id)
            if items is not None:
                db.mirror_server_work_items(body.project_id, items)  # 让新项本地可定位
            return _server_view(created)
        # server-origin 项目 + Server 不可达：别造一条会被下次 list 的镜像 DELETE 抹掉的本地行
        # （静默数据丢失 + 假成功，违反铁律#1）。如实报错让前端提示重试（WB-158）。
        raise HTTPException(503, "Server 暂不可达，任务未创建，请稍后重试")
    local_values = body.model_dump()
    _validate_local_fields(local_values)
    _sanitize_local_refs(body.project_id, None, local_values)
    wi = db.create_work_item(
        project_id=body.project_id, owner_id=user.id, title=local_values["title"], status=status, source=body.source,
        description=(body.description or "").strip(), due_date=local_values["due_date"],
        attachments=_clean_attachments(body.attachments),
        priority=priority, start_date=local_values["start_date"], labels=local_values["labels"],
        parent_id=local_values["parent_id"], milestone_id=local_values["milestone_id"],
        estimate_h=local_values["estimate_h"], spent_h=local_values["spent_h"],
        custom_fields=body.custom_fields, dependency_ids=local_values["dependency_ids"],
        sprint_id=local_values["sprint_id"],
    )
    return _view(wi, user)


@router.patch("/work-items/{item_id}")
def update_item(item_id: str, body: UpdateWorkItemBody, authorization: str = Header(default="")) -> dict:
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(400, "bad status")
    user = current_user()
    # Items belong to the project, not the creator: any writer-member may edit any
    # item in a shared project (M7 C2), so gate by project role, not item owner.
    existing = db.get_work_item(item_id)
    if not existing:
        raise HTTPException(404, "work item not found")
    _require_project_write(existing.project_id, user.id)
    if body.status == "done" and existing.status == "review":
        raise HTTPException(409, "待验收工作项只能通过交付验收完成")
    tok = _server_write_token(existing.project_id, authorization)
    if tok:
        fs = body.model_fields_set
        keys = ("title", "status", "description", "priority", "due_date",
                "start_date", "labels", "parent_id", "milestone_id", "estimate_h", "spent_h",
                "custom_fields", "dependency_ids", "sprint_id")
        patch = {k: getattr(body, k) for k in keys if k in fs and getattr(body, k) is not None}
        if "priority" in patch and patch["priority"] not in PRIORITIES:
            patch["priority"] = ""
        if "labels" in patch:
            patch["labels"] = _clean_labels(patch["labels"])
        if patch:
            up = server_client.update_work_item(tok, existing.project_id, item_id, patch)
            if up:
                items = server_client.list_work_items(tok, existing.project_id)
                if items is not None:
                    db.mirror_server_work_items(existing.project_id, items)
                return _server_view(up)
            # server-origin + Server 不可达：本地改动会被下次镜像还原，如实报错（WB-158）。
            raise HTTPException(503, "Server 暂不可达，改动未保存，请稍后重试")
        # patch 为空（仅本地字段如附件）→ 落到下方本地更新即可。
    # due_date / start_date nullable: 显式 null 清空，省略则不动。
    fields = body.model_fields_set
    local_changes = body.model_dump(exclude_unset=True)
    _validate_local_fields(local_changes, existing)
    _sanitize_local_refs(existing.project_id, item_id, local_changes)
    wi = db.update_work_item(
        item_id,
        title=local_changes.get("title"),
        status=local_changes.get("status"),
        description=local_changes.get("description"),
        due_date=local_changes.get("due_date") if "due_date" in fields else None,
        clear_due_date="due_date" in fields and not local_changes.get("due_date"),
        attachments=_clean_attachments(body.attachments) if body.attachments is not None else None,
        priority=(local_changes.get("priority") if local_changes.get("priority") in PRIORITIES else "") if "priority" in fields else None,
        start_date=local_changes.get("start_date") if "start_date" in fields else None,
        clear_start_date="start_date" in fields and not local_changes.get("start_date"),
        labels=local_changes.get("labels") if "labels" in fields else None,
        parent_id=local_changes.get("parent_id") if "parent_id" in fields else None,
        milestone_id=local_changes.get("milestone_id") if "milestone_id" in fields else None,
        estimate_h=local_changes.get("estimate_h") if "estimate_h" in fields else None,
        spent_h=local_changes.get("spent_h") if "spent_h" in fields else None,
        custom_fields=local_changes.get("custom_fields") if "custom_fields" in fields else None,
        dependency_ids=local_changes.get("dependency_ids") if "dependency_ids" in fields else None,
        sprint_id=local_changes.get("sprint_id") if "sprint_id" in fields else None,
    )
    if not wi:
        raise HTTPException(404, "work item not found")
    return _view(wi, user)


@router.delete("/work-items/{item_id}")
def delete_item(item_id: str, authorization: str = Header(default="")) -> dict:
    existing = db.get_work_item(item_id)
    if not existing:
        raise HTTPException(404, "work item not found")
    _require_project_write(existing.project_id, current_user().id)
    tok = _server_write_token(existing.project_id, authorization)
    if tok:
        if server_client.delete_work_item(tok, existing.project_id, item_id):
            items = server_client.list_work_items(tok, existing.project_id)
            if items is not None:
                db.mirror_server_work_items(existing.project_id, items)
            return {"ok": True}
        # server-origin + Server 不可达：本地删除会被下次镜像还原，如实报错（WB-158）。
        raise HTTPException(503, "Server 暂不可达，未删除，请稍后重试")
    db.delete_work_item(item_id)
    return {"ok": True}


@router.get("/work-items/{item_id}/delivery")
def get_item_delivery(item_id: str) -> dict:
    user = current_user()
    item = db.get_work_item(item_id)
    if not item or db.project_access_role(item.project_id, user.id) is None:
        raise HTTPException(404, "work item not found")
    role = db.project_access_role(item.project_id, user.id)
    runs = db.list_runs(user.id, work_item_id=item.id, limit=100)
    return {
        "work_item": _view(item, user),
        "can_write": role != Role.VIEWER,
        "launches": db.list_work_item_launches(item.id, user.id),
        "runs": [
            {
                **run.to_dict(),
                "artifacts": [artifact.to_dict() for artifact in db.list_artifacts(run.id)],
            }
            for run in runs
        ],
    }


@router.post("/work-items/{item_id}/execute")
async def execute_item(
    item_id: str, body: ExecuteWorkItemBody, authorization: str = Header(default=""),
) -> dict:
    user = current_user()
    item = db.get_work_item(item_id)
    if not item:
        raise HTTPException(404, "work item not found")
    _require_project_write(item.project_id, user.id)
    tok = _server_write_token(item.project_id, authorization)
    if tok:
        updated = await asyncio.to_thread(
            server_client.update_work_item, tok, item.project_id, item.id, {"status": "doing"}
        )
        if not updated:
            raise HTTPException(503, "Server 暂不可达，工作项未开始执行")
    key = (body.idempotency_key or str(uuid.uuid4())).strip()[:120]
    try:
        launch, created = await work_item_runner.start(
            item, user, key, model=body.model, server_token=tok,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "created": created, "launch": launch}


@router.post("/work-items/{item_id}/accept")
async def accept_item_delivery(
    item_id: str, body: AcceptWorkItemDeliveryBody,
    authorization: str = Header(default=""),
) -> dict:
    user = current_user()
    item = db.get_work_item(item_id)
    if not item:
        raise HTTPException(404, "work item not found")
    _require_project_write(item.project_id, user.id)
    if item.status != "review":
        raise HTTPException(409, "工作项尚未进入待验收状态")
    run = db.get_run_for(body.run_id, user.id)
    if not run or run.work_item_id != item.id:
        raise HTTPException(404, "run not found")
    from routers import runs as runs_router
    artifacts = [runs_router._artifact_view(value) for value in db.list_artifacts(run.id)]
    if not artifacts:
        raise HTTPException(409, "run has no artifacts")
    if any(
        value["validation_status"] != "passed"
        or not value["verification"]["exists"]
        or not value["verification"]["hash_matches"]
        for value in artifacts
    ):
        raise HTTPException(409, "artifact integrity verification failed")
    tok = _server_write_token(item.project_id, authorization)
    if tok:
        updated = await asyncio.to_thread(
            server_client.accept_work_item, tok, item.project_id, item.id,
            run_id=run.id, artifact_count=len(artifacts),
        )
        if not updated:
            raise HTTPException(503, "Server 暂不可达，交付未验收")
    try:
        accepted_item, accepted_run, accepted_artifacts = db.accept_work_item_delivery(
            item.id, run.id, user.id,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    for member in db.list_project_members(item.project_id):
        if member["user_id"] == user.id:
            continue
        db.create_notification(
            user_id=member["user_id"], kind="work_item_delivery",
            title=f"工作项已验收：{item.title}",
            body=f"{user.name} 验收了 {len(accepted_artifacts)} 个交付物。",
            project_id=item.project_id, actor_name=user.name,
        )
    return {
        "ok": True, "work_item": _view(accepted_item, user),
        "run": {**accepted_run.to_dict(), "artifacts": [a.to_dict() for a in accepted_artifacts]},
    }
