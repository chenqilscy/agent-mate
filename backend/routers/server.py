"""Server 同步端点（WB-062）。客户端用其 Server token 触发下行 pull（项目/成员镜像）。

同步 def 路由 → FastAPI 自动在线程池里跑，故内部的阻塞 Server 调用不占事件循环。
未接 Server（AGENTMATE_SERVER_URL 空）→ 直接返回 server:false，纯本地照旧。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import server_client
import server_sync
from storage import db
from storage.models import LOCAL_USER_ID

router = APIRouter(prefix="/api", tags=["server"])


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


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
    未接 Server → enabled False，纯本地照旧——前端不应因此禁用任何本地功能。

    linked 判定（WB-073）：连接模型 = 登录即以 Server 账号身份操作（app token = Server token），故先看
    **当前请求携带的 token** 能否在 Server 校验通过；命中即已连接。再兜底 LOCAL_USER 的迁移绑定
    （`server_link`，导入本地项目时才写）——两者任一即视为已连接。"""
    enabled = server_client.server_enabled()
    linked = None
    if enabled:
        acct = server_client.verify_token(_bearer(authorization))
        if acct:
            linked = {"account_id": acct.get("id", ""), "name": acct.get("name", "")}
    if linked is None:
        link = db.get_server_link(LOCAL_USER_ID)
        if link:
            linked = {"account_id": link["server_account_id"], "name": link["server_account_name"]}
    return {"enabled": enabled, "linked": linked}


# ---- 前端接 Server 的代理路由（WB-067）：前端只连本地 :8101，这里转发到 Server。全部 guarded。----

class ServerLoginBody(BaseModel):
    name: str
    password: str
    register: bool = False


@router.post("/server/login")
def server_login(body: ServerLoginBody) -> dict:
    """代理登录/注册到 Server。前端拿到返回的 token 后存为自己的 token，即以 Server 账号身份操作。"""
    if not server_client.server_enabled():
        raise HTTPException(400, "server not configured")
    res = server_client.server_login((body.name or "").strip(), body.password, body.register)
    if not res or not res.get("token"):
        raise HTTPException(401, "Server 登录失败（账号密码错误或 Server 不可达）")
    return res


@router.get("/server/projects/{project_id}/comments")
def server_comments(project_id: str, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "comments": []}
    return {"server": True, "comments": server_client.list_comments(_bearer(authorization), project_id) or []}


class CommentBody(BaseModel):
    body: str


@router.post("/server/projects/{project_id}/comments")
def server_post_comment(project_id: str, body: CommentBody, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        raise HTTPException(400, "server not configured")
    c = server_client.post_comment(_bearer(authorization), project_id, (body.body or "").strip())
    if not c:
        raise HTTPException(400, "评论失败（无权限或 Server 不可达）")
    return c


# 任务级评论代理（WB-118）：转发到 Server work-items/{wid}/comments。未接 Server → 空/报错，不崩。
@router.get("/server/projects/{project_id}/work-items/{wid}/comments")
def server_item_comments(project_id: str, wid: str, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "comments": []}
    return {"server": True, "comments": server_client.list_item_comments(_bearer(authorization), project_id, wid) or []}


@router.post("/server/projects/{project_id}/work-items/{wid}/comments")
def server_post_item_comment(project_id: str, wid: str, body: CommentBody, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        raise HTTPException(400, "server not configured")
    c = server_client.post_item_comment(_bearer(authorization), project_id, wid, (body.body or "").strip())
    if not c:
        raise HTTPException(400, "评论失败（无权限或 Server 不可达）")
    return c


@router.get("/server/projects/{project_id}/presence")
def server_presence(project_id: str, authorization: str = Header(default="")) -> dict:
    if not server_client.server_enabled():
        return {"server": False, "presence": []}
    return {"server": True, "presence": server_client.list_presence(_bearer(authorization), project_id) or []}


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
