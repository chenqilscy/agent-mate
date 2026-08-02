"""项目风险与决策台账（WB-350）。

本地项目离线自管；Server-origin 项目只读缓存、写入强制代理到 Server，失败不产生分叉。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import server_client
from project_health_service import observe_local_project_health
from auth.deps import current_user
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api", tags=["governance"])

_STATUSES = {"risk": {"open", "mitigating", "closed"},
             "decision": {"proposed", "accepted", "superseded"}}
_SEVERITIES = {"low", "medium", "high", "critical"}


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _server_token(project_id: str, authorization: str) -> str:
    project = db.get_project(project_id)
    if not project or getattr(project, "origin", "local") != "server" or not server_client.server_enabled():
        return ""
    return _bearer(authorization)


def _server_write_token(project_id: str, authorization: str) -> str:
    project = db.get_project(project_id)
    if not project or getattr(project, "origin", "local") != "server":
        return ""
    if not server_client.server_enabled():
        raise HTTPException(503, "Server 未连接，Server 项目不能在本地写入")
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "Server 项目写入需要登录凭据")
    return token


def _require_access(project_id: str, user_id: str, write: bool = False) -> None:
    role = db.project_access_role(project_id, user_id)
    if role is None:
        raise HTTPException(404, "project not found")
    if write and role == Role.VIEWER:
        raise HTTPException(403, "只读成员不能修改治理台账")
    project = db.get_project(project_id)
    if write and project and getattr(project, "archived_at", 0):
        raise HTTPException(409, "archived project is read-only")


def _validate(record_type: str, values: dict) -> None:
    if record_type not in _STATUSES or values.get("status") not in _STATUSES[record_type]:
        raise HTTPException(400, "invalid governance status")
    if record_type == "risk" and values.get("severity") not in _SEVERITIES:
        raise HTTPException(400, "invalid risk severity")
    if record_type == "decision" and values.get("severity"):
        raise HTTPException(400, "decision severity must be empty")


def _validate_local_refs(project_id: str, values: dict, changed: set[str] | None = None) -> None:
    """Validate local evidence only when it is newly assigned/changed.

    A mirrored record may reference a teammate's local Run/Artifact that this device cannot resolve;
    that must not block an unrelated title/status edit.
    """
    should = lambda key: changed is None or key in changed
    owner_id = str(values.get("owner_id") or "")
    if should("owner_id") and owner_id and owner_id not in {m["user_id"] for m in db.list_project_members(project_id)}:
        raise HTTPException(400, "owner must be an existing project member")
    work_item_id = str(values.get("work_item_id") or "")
    item = db.get_work_item(work_item_id) if work_item_id else None
    if should("work_item_id") and work_item_id and (not item or item.project_id != project_id):
        raise HTTPException(400, "work item must belong to the project")
    milestone_id = str(values.get("milestone_id") or "")
    milestone = db.get_milestone(milestone_id) if milestone_id else None
    if should("milestone_id") and milestone_id and (not milestone or milestone["project_id"] != project_id):
        raise HTTPException(400, "milestone must belong to the project")
    run_id = str(values.get("run_id") or "")
    run = db.get_run(run_id) if run_id else None
    if should("run_id") and run_id and (not run or run.project_id != project_id):
        raise HTTPException(400, "run must belong to the project")
    artifact_id = str(values.get("artifact_id") or "")
    artifact = db.get_artifact(artifact_id) if artifact_id else None
    if should("artifact_id") and artifact_id and (not artifact or artifact.project_id != project_id):
        raise HTTPException(400, "artifact must belong to the project")


class CreateBody(BaseModel):
    project_id: str
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


@router.get("/governance")
def list_records(project: str, authorization: str = Header(default="")) -> dict:
    user = current_user(); _require_access(project, user.id)
    token = _server_token(project, authorization)
    if token:
        records = server_client.list_project_governance(token, project)
        if records is not None:
            db.mirror_server_project_governance(project, records)
    return {"records": db.list_project_governance(project)}


@router.post("/governance")
def create_record(body: CreateBody, authorization: str = Header(default="")) -> dict:
    user = current_user(); _require_access(body.project_id, user.id, True)
    values = body.model_dump(exclude={"project_id"})
    values["title"] = values["title"].strip()
    values["status"] = values["status"] or ("open" if values["record_type"] == "risk" else "proposed")
    values["severity"] = values["severity"] or ("medium" if values["record_type"] == "risk" else "")
    _validate(values["record_type"], values); _validate_local_refs(body.project_id, values)
    token = _server_write_token(body.project_id, authorization)
    if token:
        created = server_client.create_project_governance(token, body.project_id, values)
        if not created:
            raise HTTPException(503, "Server 暂不可达，治理记录未创建")
        records = server_client.list_project_governance(token, body.project_id)
        if records is not None:
            db.mirror_server_project_governance(body.project_id, records)
        return created
    observe_local_project_health(body.project_id, user.id, actor_name=user.name)
    created = db.create_project_governance(project_id=body.project_id, created_by=user.id, **values)
    observe_local_project_health(body.project_id, user.id, actor_name=user.name)
    return created


@router.patch("/governance/{record_id}")
def update_record(record_id: str, body: UpdateBody, authorization: str = Header(default="")) -> dict:
    user = current_user(); current = db.get_project_governance(record_id)
    if not current:
        raise HTTPException(404, "governance record not found")
    project_id = current["project_id"]; _require_access(project_id, user.id, True)
    changes = body.model_dump(exclude_unset=True); merged = {**current, **changes}
    _validate(current["record_type"], merged); _validate_local_refs(project_id, merged, set(changes))
    token = _server_write_token(project_id, authorization)
    if token:
        updated = server_client.update_project_governance(token, project_id, record_id, changes)
        if not updated:
            raise HTTPException(503, "Server 暂不可达，治理记录未更新")
        records = server_client.list_project_governance(token, project_id)
        if records is not None:
            db.mirror_server_project_governance(project_id, records)
        return updated
    observe_local_project_health(project_id, user.id, actor_name=user.name)
    updated = db.update_project_governance(record_id, **changes) or current
    observe_local_project_health(project_id, user.id, actor_name=user.name)
    return updated


@router.delete("/governance/{record_id}")
def delete_record(record_id: str, authorization: str = Header(default="")) -> dict:
    user = current_user(); current = db.get_project_governance(record_id)
    if not current:
        raise HTTPException(404, "governance record not found")
    project_id = current["project_id"]; _require_access(project_id, user.id, True)
    token = _server_write_token(project_id, authorization)
    if token:
        if not server_client.delete_project_governance(token, project_id, record_id):
            raise HTTPException(503, "Server 暂不可达，治理记录未删除")
        records = server_client.list_project_governance(token, project_id)
        if records is not None:
            db.mirror_server_project_governance(project_id, records)
        return {"ok": True}
    observe_local_project_health(project_id, user.id, actor_name=user.name)
    db.delete_project_governance(record_id)
    observe_local_project_health(project_id, user.id, actor_name=user.name)
    return {"ok": True}
