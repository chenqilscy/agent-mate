"""项目风险与决策台账（WB-350）。

Server 是共享项目治理记录的权威源；Viewer 只读、Member+ 可写。运行/产物仅保存
local-first 证据标识和说明，不上传文件或执行内容。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account, Role, can_write

router = APIRouter(prefix="/api", tags=["governance"])

_STATUSES = {
    "risk": {"open", "mitigating", "closed"},
    "decision": {"proposed", "accepted", "superseded"},
}
_SEVERITIES = {"low", "medium", "high", "critical"}


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
    item = db.create_project_governance(project_id=project_id, created_by=account.id, **values)
    db.log_project_governance_activity(
        project_id=project_id, record_id=item["id"], actor_id=account.id,
        kind="created", detail=json.dumps({"record_type": item["record_type"], "title": item["title"]}, ensure_ascii=False),
    )
    return _decorate(item)


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
    updated = db.update_project_governance(record_id, **changes)
    if not updated:
        raise HTTPException(404, "governance record not found")
    db.log_project_governance_activity(
        project_id=project_id, record_id=record_id, actor_id=account.id,
        kind="updated", detail=json.dumps(changes, ensure_ascii=False),
    )
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
    db.delete_project_governance(record_id)
    return {"ok": True}
