"""Projects — new-project flow persisted (spec 5.1). Members/connectors auth is M7."""
from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import hub_client
from agent.skills import canonical_skill_keys
from auth.deps import current_user
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api", tags=["projects"])

# Roles allowed to manage members / edit project settings.
_MANAGE_ROLES = {Role.OWNER, Role.ADMIN}
_ROLE_CN = {"Owner": "所有者", "Admin": "管理员", "Member": "成员", "Viewer": "只读"}


# ---- Manager 写代理（WB-112c）：hub-origin 项目的成员/配置写以 Manager 为权威 ----
# 与 work_items 同模式：先本地角色 gate → 代理到 Manager → 成功后刷新本地镜像；
# Manager 不可达 → 回退纯本地（离线优先）。只写本地会被下次 pull 覆盖 = 静默丢数据，故必须代理。

def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _hub_token(project_id: str, authorization: str) -> str:
    """该项目是否走 Manager 代理：Manager 已接 + 请求带 token + 项目 origin=='hub' → bearer，否则 ""。"""
    if not hub_client.hub_enabled():
        return ""
    tok = _bearer(authorization)
    if not tok:
        return ""
    proj = db.get_project(project_id)
    if not proj or getattr(proj, "origin", "local") != "hub":
        return ""
    return tok


def _mirror_members(tok: str, project_id: str) -> None:
    mem = hub_client.list_project_members(tok, project_id)
    if mem is not None:
        db.replace_hub_project_members(project_id, mem)


def _mirror_project(p: dict) -> None:
    """把 Manager 返回的项目 dict 刷进本地镜像（origin='hub'）。"""
    db.mirror_hub_project(
        id=p.get("id", ""), name=p.get("name", ""), owner_id=p.get("owner_id", ""),
        instruction=p.get("instruction", ""), connectors=p.get("connectors"),
        experts=p.get("experts"), skills=canonical_skill_keys(p.get("skills") or []),
    )


def _require_access(project_id: str, user_id: str) -> Role:
    """Return the caller's effective role in the project, or 404 if no access."""
    role = db.project_access_role(project_id, user_id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_manage(project_id: str, user_id: str) -> Role:
    role = _require_access(project_id, user_id)
    if role not in _MANAGE_ROLES:
        raise HTTPException(403, "需要管理员或所有者权限")
    return role


def _member_role(raw: str) -> Role:
    """Validate an assignable membership role (Owner is not assignable)."""
    try:
        r = Role(raw)
    except ValueError:
        raise HTTPException(400, "无效角色")
    if r == Role.OWNER:
        raise HTTPException(400, "不能指派所有者角色")
    return r


class CreateProjectBody(BaseModel):
    name: str
    instruction: str = ""
    connectors: list[str] = []
    experts: list[str] = []
    skills: list[str] = []
    knowledge_ids: list[str] = []


class UpdateProjectBody(BaseModel):
    name: str | None = None
    instruction: str | None = None
    connectors: list[str] | None = None
    experts: list[str] | None = None
    skills: list[str] | None = None
    knowledge_ids: list[str] | None = None


class AddMemberBody(BaseModel):
    name: str
    role: str = "Member"


class UpdateMemberBody(BaseModel):
    role: str


def _ago(ts: float) -> str:
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _view(p, role: Role | None = None) -> dict:
    d = p.to_dict()
    d["ago"] = _ago(p.created_at)
    if role is not None:
        # The caller's role in this project — the UI uses it for a badge and to
        # gate management actions (Owner/Admin can manage members & settings).
        d["role"] = role.value
    return d


@router.get("/projects")
def list_projects() -> dict:
    user = current_user()
    # Owned + projects shared to the caller (M7 C2), each with their role.
    return {"projects": [_view(p, role) for (p, role) in db.list_projects_for(user.id)]}


@router.post("/projects")
def create_project(body: CreateProjectBody) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "empty project name")
    user = current_user()
    p = db.create_project(
        owner_id=user.id,
        name=name,
        instruction=body.instruction,
        connectors=body.connectors,
        experts=body.experts,
        skills=canonical_skill_keys(body.skills),
        knowledge_ids=list(dict.fromkeys(body.knowledge_ids))[:20],
    )
    return _view(p, Role.OWNER)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    # Access = owner OR member (M7 C2); a project you can't see 404s, not leaks config.
    role = _require_access(project_id, current_user().id)
    p = db.get_project(project_id)
    assert p is not None
    return _view(p, role)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: UpdateProjectBody, authorization: str = Header(default="")) -> dict:
    role = _require_manage(project_id, current_user().id)
    tok = _hub_token(project_id, authorization)
    if tok:
        patch = body.model_dump(exclude_unset=True)
        if "skills" in patch:
            patch["skills"] = canonical_skill_keys(patch["skills"] or [])
        # knowledge_ids 是本机 WeKnora 执行配置，绝不上云；Manager 只收协作元数据。
        local_knowledge = patch.pop("knowledge_ids", None)
        up = hub_client.update_project(tok, project_id, patch) if patch else db.get_project(project_id).to_dict()
        if up:
            if patch:
                _mirror_project(up)
            if local_knowledge is not None:
                db.update_project(project_id, knowledge_ids=list(dict.fromkeys(local_knowledge))[:20])
            return _view(db.get_project(project_id), role)
        # Manager 不可达 → 回退本地
    updated = db.update_project(
        project_id,
        name=body.name,
        instruction=body.instruction,
        connectors=body.connectors,
        experts=body.experts,
        skills=canonical_skill_keys(body.skills) if body.skills is not None else None,
        knowledge_ids=list(dict.fromkeys(body.knowledge_ids))[:20] if body.knowledge_ids is not None else None,
    )
    return _view(updated, role)


@router.get("/projects/{project_id}/sessions")
def project_sessions(project_id: str) -> dict:
    _require_access(project_id, current_user().id)
    rows = db.list_project_sessions(project_id)
    # Attribute each run to who started it (M7 C3 activity feed). Names cached so
    # a busy project's feed doesn't hit users N times.
    names: dict[str, str] = {}

    def owner_name(uid: str) -> str:
        if uid not in names:
            u = db.get_user(uid)
            names[uid] = u.name if u else uid
        return names[uid]

    return {"sessions": [
        {**s.to_dict(), "ago": _ago(s.updated_at), "owner_name": owner_name(s.owner_id)}
        for s in rows
    ]}


# ---- members (M7 C2) ----------------------------------------------------

@router.get("/projects/{project_id}/members")
def list_members(project_id: str) -> dict:
    _require_access(project_id, current_user().id)
    return {"members": db.list_project_members(project_id)}


@router.post("/projects/{project_id}/members")
def add_member(project_id: str, body: AddMemberBody, authorization: str = Header(default="")) -> dict:
    me = current_user()
    _require_manage(project_id, me.id)
    role = _member_role(body.role)
    tok = _hub_token(project_id, authorization)
    if tok:
        # Manager 按账号名解析成员（可加尚未镜像到本地的 Manager 账号）；成功后刷新本地成员镜像。
        res = hub_client.add_member(tok, project_id, (body.name or "").strip(), role.value)
        if res is not None:
            _mirror_members(tok, project_id)
            return {"members": db.list_project_members(project_id)}
        # Manager 不可达 → 回退本地
    found = db.get_user_by_name((body.name or "").strip())
    if not found:
        raise HTTPException(404, "用户不存在")
    target = found[0]
    p = db.get_project(project_id)
    if p and target.id == p.owner_id:
        raise HTTPException(400, "该用户已是项目所有者")
    db.add_project_member(project_id, target.id, role)
    # M7 C4: tell the invitee, in their message center.
    if p:
        db.create_notification(
            user_id=target.id, kind="member_added",
            title=f"{me.name} 邀请你加入项目「{p.name}」",
            body=f"你的角色：{_ROLE_CN.get(role.value, role.value)}",
            project_id=project_id, actor_name=me.name,
        )
    return {"members": db.list_project_members(project_id)}


@router.patch("/projects/{project_id}/members/{user_id}")
def update_member(project_id: str, user_id: str, body: UpdateMemberBody, authorization: str = Header(default="")) -> dict:
    me = current_user()
    _require_manage(project_id, me.id)
    role = _member_role(body.role)
    tok = _hub_token(project_id, authorization)
    if tok:
        # hub-origin 项目里 user_id 即 Manager account id（镜像时同 id）。
        if hub_client.update_member(tok, project_id, user_id, role.value) is not None:
            _mirror_members(tok, project_id)
            return {"members": db.list_project_members(project_id)}
        # Manager 不可达 → 回退本地
    if db.project_member_role(project_id, user_id) is None:
        raise HTTPException(404, "成员不存在")
    db.add_project_member(project_id, user_id, role)  # upsert = change role
    p = db.get_project(project_id)
    if p and user_id != me.id:
        db.create_notification(
            user_id=user_id, kind="role_changed",
            title=f"你在项目「{p.name}」的角色调整为 {_ROLE_CN.get(role.value, role.value)}",
            project_id=project_id, actor_name=me.name,
        )
    return {"members": db.list_project_members(project_id)}


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(project_id: str, user_id: str, authorization: str = Header(default="")) -> dict:
    me = current_user()
    # Leaving (removing yourself) needs only access; removing others needs manage.
    if user_id == me.id:
        _require_access(project_id, me.id)
    else:
        _require_manage(project_id, me.id)
    tok = _hub_token(project_id, authorization)
    if tok:
        if hub_client.remove_member(tok, project_id, user_id):
            _mirror_members(tok, project_id)
            return {"ok": True}
        # Manager 不可达 → 回退本地
    if user_id == me.id:
        db.remove_project_member(project_id, user_id)
        return {"ok": True}
    p = db.get_project(project_id)
    db.remove_project_member(project_id, user_id)
    if p:
        db.create_notification(
            user_id=user_id, kind="member_removed",
            title=f"你已被移出项目「{p.name}」",
            project_id=project_id, actor_name=me.name,
        )
    return {"ok": True}
