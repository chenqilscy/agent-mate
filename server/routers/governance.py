"""项目风险与决策台账（WB-350）。

Server 是共享项目治理记录的权威源；Viewer 只读、Member+ 可写。运行/产物仅保存
local-first 证据标识和说明，不上传文件或执行内容。
"""
from __future__ import annotations

import json
from datetime import date
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account, Role, can_write
from project_health_service import observe_project_health

router = APIRouter(prefix="/api", tags=["governance"])

_STATUSES = {
    "risk": {"open", "mitigating", "closed"},
    "decision": {"proposed", "accepted", "superseded"},
}
_SEVERITIES = {"low", "medium", "high", "critical"}
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_ACTION_TASK_PRIORITY = {"low": "low", "medium": "medium", "high": "high", "critical": "urgent"}
_ACTION_TASK_LOCK = Lock()


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


def _validate_refs(project_id: str, values: dict) -> None:
    owner_id = str(values.get("owner_id") or "").strip()
    if owner_id:
        members = {item["account_id"] for item in db.list_project_members(project_id)}
        if owner_id not in members:
            raise HTTPException(400, "owner must be an existing project member")
    work_item_id = str(values.get("work_item_id") or "").strip()
    if work_item_id:
        item = db.get_work_item(work_item_id)
        if not item or item["project_id"] != project_id:
            raise HTTPException(400, "work item must belong to the project")
    milestone_id = str(values.get("milestone_id") or "").strip()
    if milestone_id:
        milestone = db.get_milestone(milestone_id)
        if not milestone or milestone["project_id"] != project_id:
            raise HTTPException(400, "milestone must belong to the project")


def _validate(record_type: str, values: dict) -> None:
    if record_type not in _STATUSES:
        raise HTTPException(400, "invalid record_type")
    if "status" in values and values["status"] not in _STATUSES[record_type]:
        raise HTTPException(400, "invalid status for record type")
    if record_type == "risk":
        if values.get("severity") not in _SEVERITIES:
            raise HTTPException(400, "invalid risk severity")
    elif values.get("severity"):
        raise HTTPException(400, "decision severity must be empty")


def _validate_risk_closure(project_id: str, values: dict) -> dict | None:
    if values.get("record_type") != "risk" or values.get("status") != "closed":
        return None
    if not str(values.get("response") or "").strip():
        raise HTTPException(409, "关闭风险前必须填写应对措施")
    work_item_id = str(values.get("work_item_id") or "").strip()
    if not work_item_id:
        raise HTTPException(409, "关闭风险前必须关联处置任务")
    work_item = db.get_work_item(work_item_id)
    if not work_item or work_item["project_id"] != project_id:
        raise HTTPException(409, "关联的处置任务不存在")
    acceptance = db.get_work_item_acceptance(work_item_id)
    if work_item.get("status") != "done" or not acceptance:
        raise HTTPException(409, "处置任务通过真实交付验收后才能关闭风险")
    if not str(values.get("evidence_label") or "").strip():
        raise HTTPException(409, "关闭风险前必须填写残余风险结论与证据说明")
    run_id = str(values.get("run_id") or "").strip()
    if run_id and run_id != str(acceptance.get("run_id") or ""):
        raise HTTPException(409, "风险证据 Run 必须与处置任务验收 Run 一致")
    return acceptance


def _decorate(item: dict) -> dict:
    members = {m["account_id"]: m.get("name", "") for m in db.list_project_members(item["project_id"])}
    work_item = db.get_work_item(item.get("work_item_id") or "")
    milestone = db.get_milestone(item.get("milestone_id") or "")
    return {
        **item,
        "owner_name": members.get(item.get("owner_id") or "", ""),
        "work_item_title": work_item.get("title", "") if work_item else "",
        "milestone_name": milestone.get("name", "") if milestone else "",
    }


def _decorate_action_task(project_id: str, item: dict) -> dict:
    members = {m["account_id"]: m.get("name", "") for m in db.list_project_members(project_id)}
    return {
        **item,
        "assignee_name": members.get(str(item.get("assignee") or ""), str(item.get("assignee") or "")),
        "attachments": [],
        "delivery_accepted": db.get_work_item_acceptance(item["id"]) is not None,
    }


def _notify_risk_escalation(project_id: str, item: dict, account: Account,
                            previous: dict | None = None) -> None:
    """Notify on first high/critical entry or upward escalation; reads never write."""
    if item.get("record_type") != "risk" or item.get("status") == "closed":
        return
    severity = str(item.get("severity") or "")
    if severity not in {"high", "critical"}:
        return
    previous_active = bool(previous and previous.get("status") != "closed")
    previous_rank = _SEVERITY_RANK.get(str(previous.get("severity") or ""), 0) if previous_active else 0
    if previous is not None and _SEVERITY_RANK[severity] <= previous_rank:
        return
    label = "严重" if severity == "critical" else "高"
    for member in db.list_project_members(project_id):
        account_id = member["account_id"]
        if account_id == account.id:
            continue
        db.add_notification(
            account_id=account_id,
            kind="project_risk",
            title=f"项目出现{label}风险",
            body=str(item.get("title") or "")[:200],
            project_id=project_id,
            actor_name=account.name,
            dedupe_key=f"project-risk:{item['id']}:{severity}",
        )


class CreateBody(BaseModel):
    record_type: str
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    status: str = ""
    severity: str = ""
    owner_id: str = ""
    response: str = Field(default="", max_length=20000)
    rationale: str = Field(default="", max_length=20000)
    work_item_id: str = ""
    milestone_id: str = ""
    run_id: str = Field(default="", max_length=100)
    artifact_id: str = Field(default="", max_length=100)
    evidence_label: str = Field(default="", max_length=500)


class UpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    status: str | None = None
    severity: str | None = None
    owner_id: str | None = None
    response: str | None = Field(default=None, max_length=20000)
    rationale: str | None = Field(default=None, max_length=20000)
    work_item_id: str | None = None
    milestone_id: str | None = None
    run_id: str | None = Field(default=None, max_length=100)
    artifact_id: str | None = Field(default=None, max_length=100)
    evidence_label: str | None = Field(default=None, max_length=500)


class ActionTaskBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_date: str = ""
    acceptance_criteria: str = Field(min_length=1, max_length=10000)


@router.get("/projects/{project_id}/governance")
def list_records(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"records": [_decorate(item) for item in db.list_project_governance(project_id)]}


@router.get("/projects/{project_id}/governance/activity")
def list_activity(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_project_governance_activity(project_id)}


@router.post("/projects/{project_id}/governance")
def create_record(project_id: str, body: CreateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    values = body.model_dump()
    values["record_type"] = values["record_type"].strip()
    values["title"] = values["title"].strip()
    if not values["title"]:
        raise HTTPException(400, "empty title")
    if not values["status"]:
        values["status"] = "open" if values["record_type"] == "risk" else "proposed"
    if values["record_type"] == "risk" and not values["severity"]:
        values["severity"] = "medium"
    _validate(values["record_type"], values)
    _validate_refs(project_id, values)
    observe_project_health(project_id, actor_name=account.name)
    item = db.create_project_governance(project_id=project_id, created_by=account.id, **values)
    db.log_project_governance_activity(
        project_id=project_id, record_id=item["id"], actor_id=account.id,
        kind="created", detail=json.dumps({"record_type": item["record_type"], "title": item["title"]}, ensure_ascii=False),
    )
    _notify_risk_escalation(project_id, item, account)
    observe_project_health(project_id, actor_name=account.name)
    return _decorate(item)


@router.post("/projects/{project_id}/governance/{record_id}/action-task")
def create_action_task(project_id: str, record_id: str, body: ActionTaskBody,
                       account: Account = CurrentAccount) -> dict:
    """Idempotently create and link the executable task for one risk."""
    _require_write(project_id, account)
    title = body.title.strip()
    criteria = body.acceptance_criteria.strip()
    due_date = body.due_date.strip()
    if not title or not criteria:
        raise HTTPException(400, "task title and acceptance criteria are required")
    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError as exc:
            raise HTTPException(400, "invalid due_date") from exc
    with _ACTION_TASK_LOCK:
        current = db.get_project_governance(record_id)
        if not current or current["project_id"] != project_id:
            raise HTTPException(404, "governance record not found")
        if current["record_type"] != "risk" or current["status"] == "closed":
            raise HTTPException(409, "only an active risk can create an action task")
        if current.get("work_item_id"):
            linked = db.get_work_item(current["work_item_id"])
            if linked:
                return {"created": False, "work_item": _decorate_action_task(project_id, linked), "risk": _decorate(current)}
        source = f"risk:{record_id}"
        existing = next((item for item in db.list_work_items(project_id) if item.get("source") == source), None)
        if existing:
            linked_risk = db.update_project_governance(record_id, work_item_id=existing["id"])
            return {"created": False, "work_item": _decorate_action_task(project_id, existing), "risk": _decorate(linked_risk or current)}
        description = "\n\n".join(part for part in (
            f"## 来源风险\n\n**{current['title']}**",
            str(current.get("description") or "").strip(),
            f"## 应对措施\n\n{str(current.get('response') or '').strip() or '- 待补充'}",
            f"## 验收标准\n\n{criteria}",
            "## 证据要求\n\n- [ ] 通过真实 Run 完成任务交付\n- [ ] 交付物完整性校验通过\n- [ ] 风险关闭前补充残余风险结论",
        ) if part)
        item = db.create_work_item(
            project_id=project_id, title=title, status="todo", source=source,
            assignee=str(current.get("owner_id") or ""), description=description,
            priority=_ACTION_TASK_PRIORITY[str(current.get("severity") or "medium")],
            due_date=due_date, labels=["风险处置"],
            milestone_id=str(current.get("milestone_id") or ""),
        )
        linked_risk = db.update_project_governance(record_id, work_item_id=item["id"])
        db.log_work_item_activity(
            project_id=project_id, work_item_id=item["id"], actor=account.name,
            kind="created", detail=item["title"],
        )
        db.log_project_governance_activity(
            project_id=project_id, record_id=record_id, actor_id=account.id,
            kind="action_task_created", detail=json.dumps({"work_item_id": item["id"]}, ensure_ascii=False),
        )
        observe_project_health(project_id, actor_name=account.name)
        return {"created": True, "work_item": _decorate_action_task(project_id, item), "risk": _decorate(linked_risk or current)}


@router.patch("/projects/{project_id}/governance/{record_id}")
def update_record(project_id: str, record_id: str, body: UpdateBody,
                  account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    current = db.get_project_governance(record_id)
    if not current or current["project_id"] != project_id:
        raise HTTPException(404, "governance record not found")
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes:
        changes["title"] = str(changes["title"] or "").strip()
        if not changes["title"]:
            raise HTTPException(400, "empty title")
    merged = {**current, **changes}
    _validate(current["record_type"], merged)
    _validate_refs(project_id, merged)
    acceptance = _validate_risk_closure(project_id, merged)
    if acceptance and not str(merged.get("run_id") or "").strip():
        changes["run_id"] = str(acceptance.get("run_id") or "")
    observe_project_health(project_id, actor_name=account.name)
    updated = db.update_project_governance(record_id, **changes)
    if not updated:
        raise HTTPException(404, "governance record not found")
    db.log_project_governance_activity(
        project_id=project_id, record_id=record_id, actor_id=account.id,
        kind="updated", detail=json.dumps(changes, ensure_ascii=False),
    )
    _notify_risk_escalation(project_id, updated, account, current)
    observe_project_health(project_id, actor_name=account.name)
    return _decorate(updated)


@router.delete("/projects/{project_id}/governance/{record_id}")
def delete_record(project_id: str, record_id: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    current = db.get_project_governance(record_id)
    if not current or current["project_id"] != project_id:
        raise HTTPException(404, "governance record not found")
    # 保留不可变的删除审计；activity 不对 record_id 建外键，项目删除时再统一清理。
    db.log_project_governance_activity(
        project_id=project_id, record_id=record_id, actor_id=account.id,
        kind="deleted", detail=json.dumps({"record_type": current["record_type"], "title": current["title"]}, ensure_ascii=False),
    )
    observe_project_health(project_id, actor_name=account.name)
    db.delete_project_governance(record_id)
    observe_project_health(project_id, actor_name=account.name)
    return {"ok": True}
