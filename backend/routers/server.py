"""Server 同步端点（WB-062）。客户端用其 Server token 触发下行 pull（项目/成员镜像）。

同步 def 路由 → FastAPI 自动在线程池里跑，故内部的阻塞 Server 调用不占事件循环。
未接 Server（AGENTMATE_SERVER_URL 空）→ 直接返回 server:false；本机访客执行能力不受影响。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import server_client
import server_sync
from auth.deps import current_user
from storage import db
from config import settings

router = APIRouter(prefix="/api", tags=["server"])


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _required_server_token(authorization: str) -> str:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="server identity required")
    return token


@router.post("/server/pull")
def server_pull(authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "synced": 0, "projects": []}
    token = _bearer(authorization)
    # 先拉技能定义，再归一项目 skills；这样旧 Server 项目里的展示名也能借 APP_SKILLS 映射成 slug。
    catalog = server_sync.pull_catalog(token)        # 下行：目录/技能定义（WB-066/183）
    result = server_sync.pull(token)                 # 下行：拉项目/成员镜像
    flushed = server_sync.flush_outbox()             # 上行：顺手补推 outbox（同步路由=线程池）
    return {
        "server": True, **result, "flushed": flushed.get("pushed", 0),
        "catalog": catalog.get("downlinked", 0), "skills": catalog.get("skills", 0),
        "connectors": catalog.get("connectors", 0),
        "experts": catalog.get("experts", 0),
    }


@router.post("/server/import")
def server_import(authorization: str = Header(default="")) -> dict:
    """存量导入（WB-063）：把本机 LOCAL_USER 的本地原生项目上行到 Server，幂等。需带有效 Server token。"""
    if not server_client.server_enabled():
        return {"server": False, "imported": 0, "skipped": 0}
    acct = server_client.verify_token(_bearer(authorization))
    if not acct:
        raise HTTPException(401, "invalid or missing server token")
    return server_sync.import_local_to_server(_bearer(authorization), acct)


@router.get("/server/status")
def server_status(authorization: str = Header(default="")) -> dict:
    """本地是否已接 Server、当前是否已以某 Server 账号连接（前端据此显示同步/导入入口 + 解锁协作 UI）。
    linked 只代表当前 Bearer token 对应的 Server 身份；LOCAL_USER 的存量导入映射不是登录态。
    Server 暂不可达或地址被清除时，已验证 token 仍从本地身份镜像恢复，避免把已登录用户误报为访客。"""
    enabled = server_client.server_enabled()
    linked = None
    token = _bearer(authorization)
    auth_state = "unconfigured" if not enabled else "disconnected"
    cache = db.cached_server_token_status(token) if token else None
    cached_user_id = db.cached_server_user(
        token, max_validation_age=settings.SERVER_TOKEN_OFFLINE_GRACE_SECONDS,
    ) if token else None
    if cached_user_id:
        cached_user = db.get_user(cached_user_id)
        if cached_user:
            linked = {"account_id": cached_user.id, "name": cached_user.name}
            auth_state = "offline_grace"
    if enabled and token:
        state, acct = server_client.verify_token_state(token)
        if state == "invalid":
            db.revoke_cached_server_token(token)
            linked = None
            auth_state = "revoked"
        elif acct:
            linked = {"account_id": acct.get("id", ""), "name": acct.get("name", "")}
            account_id = str(acct.get("id") or "")
            if account_id:
                db.upsert_external_user(
                    account_id, str(acct.get("name") or ""), str(acct.get("plan") or "体验版"),
                )
                db.cache_token(token, account_id, acct.get("_token_expires_at"))
                db.set_server_identity(account_id, token)
            auth_state = "online"
        elif state == "unavailable" and linked is None:
            auth_state = "offline_expired"
    now = time.time()
    remaining = 0
    if auth_state == "offline_grace" and cache:
        remaining = max(
            0, int(float(cache["validated_at"]) + settings.SERVER_TOKEN_OFFLINE_GRACE_SECONDS - now),
        )
    return {
        "enabled": enabled,
        # Console 与 Server 同源部署；仅返回可导航的 origin，不返回 token 或其他凭据。
        "console_url": settings.AGENTMATE_SERVER_URL.rstrip("/") if enabled else "",
        "linked": linked,
        "auth_state": auth_state,
        "online_validation_ttl_seconds": settings.SERVER_TOKEN_VALIDATION_TTL_SECONDS,
        "offline_grace_seconds": settings.SERVER_TOKEN_OFFLINE_GRACE_SECONDS,
        "offline_grace_remaining_seconds": remaining,
    }


# ---- 前端接 Server 的代理路由（WB-067）：前端只连本地 :8101，这里转发到 Server。全部 guarded。----

class ServerLoginBody(BaseModel):
    name: str
    password: str
    create_account: bool = Field(default=False, alias="register")


@router.post("/server/login")
def server_login(body: ServerLoginBody) -> dict:
    """代理登录/注册到 Server。前端拿到返回的 token 后存为自己的 token，即以 Server 账号身份操作。"""
    if not server_client.server_enabled():
        raise HTTPException(400, "server not configured")
    status, result = server_client.server_login_ex(
        (body.name or "").strip(), body.password, body.create_account,
    )
    if status == "ok" and result and result.get("token"):
        return result
    if status == "rejected" and result:
        raise HTTPException(int(result.get("code") or 400), result.get("detail") or "Server 拒绝登录")
    raise HTTPException(503, "Server 暂不可达，请稍后重试")


@router.get("/server/projects/{project_id}/comments")
def server_comments(project_id: str, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "comments": []}
    comments = server_client.list_comments(_required_server_token(authorization), project_id)
    if comments is None:
        raise HTTPException(503, "Server 暂不可达，评论未加载")
    return {"server": True, "comments": comments}


class CommentBody(BaseModel):
    body: str


@router.post("/server/projects/{project_id}/comments")
def server_post_comment(project_id: str, body: CommentBody, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        raise HTTPException(400, "server not configured")
    c = server_client.post_comment(
        _required_server_token(authorization), project_id, (body.body or "").strip()
    )
    if not c:
        raise HTTPException(503, "Server 暂不可达，评论未提交")
    return c


# 任务级评论代理（WB-118）：转发到 Server work-items/{wid}/comments。未接 Server → 空/报错，不崩。
@router.get("/server/projects/{project_id}/work-items/{wid}/comments")
def server_item_comments(project_id: str, wid: str, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "comments": []}
    comments = server_client.list_item_comments(
        _required_server_token(authorization), project_id, wid
    )
    if comments is None:
        raise HTTPException(503, "Server 暂不可达，任务评论未加载")
    return {"server": True, "comments": comments}


@router.post("/server/projects/{project_id}/work-items/{wid}/comments")
def server_post_item_comment(project_id: str, wid: str, body: CommentBody, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        raise HTTPException(400, "server not configured")
    c = server_client.post_item_comment(
        _required_server_token(authorization), project_id, wid, (body.body or "").strip()
    )
    if not c:
        raise HTTPException(503, "Server 暂不可达，任务评论未提交")
    return c


@router.get("/server/projects/{project_id}/presence")
def server_presence(project_id: str, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "presence": []}
    presence = server_client.list_presence(_required_server_token(authorization), project_id)
    if presence is None:
        raise HTTPException(503, "Server 暂不可达，在线状态未加载")
    return {"server": True, "presence": presence}


@router.get("/server/projects/{project_id}/timeline")
def server_timeline(project_id: str, authorization: str = Header(default="")) -> dict:
    """App 动态回读 Server 时间线；网络失败返回 last-known-good 缓存，不泄漏其他项目。"""
    user = current_user()
    project = db.get_project_for(project_id, user.id)
    if not project:
        raise HTTPException(404, "project not found")
    token = _bearer(authorization)
    if project.origin == "server" and (not token or db.user_id_for_token(token) != user.id):
        # AuthMiddleware 对无效/缺失 token 会回到 local owner；Server 私有缓存不能继承该单机回退。
        raise HTTPException(401, "server identity required")
    cached = db.list_server_timeline(project_id)
    if project.origin != "server" or not server_client.server_enabled():
        return {"server": False, "reachable": False, "stale": bool(cached), "events": cached}
    events = server_client.list_timeline(token, project_id)
    if events is None:
        return {"server": True, "reachable": False, "stale": bool(cached), "events": cached}
    db.mirror_server_timeline(project_id, events)
    return {"server": True, "reachable": True, "stale": False, "events": db.list_server_timeline(project_id)}


def _server_project_read_token(project_id: str, authorization: str) -> str:
    """Guard metadata reads to a locally mirrored Server project and identity token."""
    user = current_user()
    project = db.get_project_for(project_id, user.id)
    if not project:
        raise HTTPException(404, "project not found")
    token = _required_server_token(authorization)
    if project.origin != "server" or not server_client.server_enabled():
        raise HTTPException(400, "not a Server project")
    if db.user_id_for_token(token) != user.id:
        raise HTTPException(401, "server identity required")
    return token


@router.get("/server/projects/{project_id}/activity")
def server_project_activity(project_id: str, authorization: str = Header(default="")) -> dict:
    events = server_client.list_project_activity(
        _server_project_read_token(project_id, authorization), project_id,
    )
    if events is None:
        raise HTTPException(503, "Server 暂不可达，项目活动未加载")
    return {"server": True, "activity": events}


@router.get("/server/projects/{project_id}/custom-fields")
def server_project_custom_fields(project_id: str, authorization: str = Header(default="")) -> dict:
    fields = server_client.list_project_custom_fields(
        _server_project_read_token(project_id, authorization), project_id,
    )
    if fields is None:
        raise HTTPException(503, "Server 暂不可达，项目字段未加载")
    return {"server": True, "fields": fields}


@router.get("/server/projects/{project_id}/sprints")
def server_project_sprints(project_id: str, authorization: str = Header(default="")) -> dict:
    sprints = server_client.list_project_sprints(
        _server_project_read_token(project_id, authorization), project_id,
    )
    if sprints is None:
        raise HTTPException(503, "Server 暂不可达，项目 Sprint 未加载")
    return {"server": True, "sprints": sprints}


@router.get("/server/projects/{project_id}/pm-preferences")
def server_project_pm_preferences(project_id: str, authorization: str = Header(default="")) -> dict:
    preferences = server_client.get_project_pm_preferences(
        _server_project_read_token(project_id, authorization), project_id,
    )
    if preferences is None:
        raise HTTPException(503, "Server 暂不可达，项目工作台偏好未加载")
    return {"server": True, "preferences": preferences}


class ServerPmPreferencesBody(BaseModel):
    templates: list[dict] | None = None
    views: list[dict] | None = None
    wip: dict[str, int] | None = None
    expected_shared_updated_at: float | None = None
    expected_views_updated_at: float | None = None


class ServerCustomFieldBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    field_type: str = "text"
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = False


class ServerCustomFieldUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    field_type: str | None = None
    options: list[str] | None = Field(default=None, max_length=50)
    required: bool | None = None


class ServerSprintBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(default="", max_length=1000)
    milestone_id: str = Field(default="", max_length=100)
    start_date: str
    end_date: str
    status: str = "planned"


class ServerSprintUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal: str | None = Field(default=None, max_length=1000)
    milestone_id: str | None = Field(default=None, max_length=100)
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None


def _server_write(call, unavailable_message: str):
    try:
        result = call()
    except server_client.ServerRejected as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    if result is None or result is False:
        raise HTTPException(503, unavailable_message)
    return result


@router.put("/server/projects/{project_id}/pm-preferences")
def server_update_project_pm_preferences(project_id: str, body: ServerPmPreferencesBody,
                                          authorization: str = Header(default="")) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "PM preference patch is empty")
    token = _server_project_read_token(project_id, authorization)
    preferences = _server_write(
        lambda: server_client.update_project_pm_preferences(token, project_id, values),
        "Server 暂不可达，项目工作台偏好未保存",
    )
    return {"server": True, "preferences": preferences}


@router.post("/server/projects/{project_id}/custom-fields")
def server_create_project_custom_field(project_id: str, body: ServerCustomFieldBody,
                                       authorization: str = Header(default="")) -> dict:
    token = _server_project_read_token(project_id, authorization)
    field = _server_write(
        lambda: server_client.create_project_custom_field(token, project_id, body.model_dump()),
        "Server 暂不可达，项目字段未保存",
    )
    return {"server": True, "field": field}


@router.patch("/server/projects/{project_id}/custom-fields/{field_id}")
def server_update_project_custom_field(project_id: str, field_id: str, body: ServerCustomFieldUpdateBody,
                                       authorization: str = Header(default="")) -> dict:
    token = _server_project_read_token(project_id, authorization)
    field = _server_write(
        lambda: server_client.update_project_custom_field(token, project_id, field_id, body.model_dump(exclude_unset=True)),
        "Server 暂不可达，项目字段未保存",
    )
    return {"server": True, "field": field}


@router.delete("/server/projects/{project_id}/custom-fields/{field_id}")
def server_delete_project_custom_field(project_id: str, field_id: str,
                                       authorization: str = Header(default="")) -> dict:
    token = _server_project_read_token(project_id, authorization)
    _server_write(
        lambda: server_client.delete_project_custom_field(token, project_id, field_id),
        "Server 暂不可达，项目字段未删除",
    )
    return {"server": True, "ok": True}


@router.post("/server/projects/{project_id}/sprints")
def server_create_project_sprint(project_id: str, body: ServerSprintBody,
                                 authorization: str = Header(default="")) -> dict:
    token = _server_project_read_token(project_id, authorization)
    sprint = _server_write(
        lambda: server_client.create_project_sprint(token, project_id, body.model_dump()),
        "Server 暂不可达，项目 Sprint 未保存",
    )
    return {"server": True, "sprint": sprint}


@router.patch("/server/projects/{project_id}/sprints/{sprint_id}")
def server_update_project_sprint(project_id: str, sprint_id: str, body: ServerSprintUpdateBody,
                                 authorization: str = Header(default="")) -> dict:
    token = _server_project_read_token(project_id, authorization)
    sprint = _server_write(
        lambda: server_client.update_project_sprint(token, project_id, sprint_id, body.model_dump(exclude_unset=True)),
        "Server 暂不可达，项目 Sprint 未保存",
    )
    return {"server": True, "sprint": sprint}


@router.delete("/server/projects/{project_id}/sprints/{sprint_id}")
def server_delete_project_sprint(project_id: str, sprint_id: str,
                                 authorization: str = Header(default="")) -> dict:
    token = _server_project_read_token(project_id, authorization)
    _server_write(
        lambda: server_client.delete_project_sprint(token, project_id, sprint_id),
        "Server 暂不可达，项目 Sprint 未删除",
    )
    return {"server": True, "ok": True}


@router.get("/server/projects/{project_id}/sync-conflicts")
def server_sync_conflicts(project_id: str, authorization: str = Header(default="")) -> dict:
    """返回当前用户可访问项目的镜像分叉，供 UI/诊断明确展示而非静默覆盖。"""
    user = current_user()
    project = db.get_project_for(project_id, user.id)
    if not project:
        raise HTTPException(404, "project not found")
    token = _bearer(authorization)
    if project.origin == "server" and (not token or db.user_id_for_token(token) != user.id):
        raise HTTPException(401, "server identity required")
    conflicts = db.list_server_sync_conflicts(project_id)
    return {"conflicts": conflicts, "count": len(conflicts)}


@router.get("/server/notifications")
def server_notifications(authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "notifications": [], "unread": 0}
    d = server_client.server_notifications(_bearer(authorization)) or {}
    return {"server": True, "notifications": d.get("notifications", []), "unread": d.get("unread", 0)}


class MarkBody(BaseModel):
    ids: list[str] | None = None


@router.post("/server/notifications/read")
def server_mark_read(body: MarkBody, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"ok": False}
    return {"ok": server_client.mark_server_notifications(_bearer(authorization), body.ids)}
