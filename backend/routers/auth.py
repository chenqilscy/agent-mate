"""AgentMate account bridge.

Server is the only account authority: App login/register always delegates to
Server and mirrors the verified account locally. The local ``users`` row and
cached Server token support owner-scoped execution and an already-authenticated
offline session; they are not a second account system. Requests without a token
use ``LOCAL_USER`` only as an anonymous guest scope.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import server_client
from storage import db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    name: str
    password: str


class LoginBody(BaseModel):
    name: str
    password: str


def _user_view(user) -> dict:
    return {"id": user.id, "name": user.name, "role": user.role.value, "plan": user.plan}


def _mirror_server_account(token: str, acct: dict, expires_at: float | None = None) -> dict:
    """把 Console 校验过的账号镜像进本地 users + 缓存 Server token（后续请求本地命中，不再打 Console），
    并记住 Server 身份供后台 outbox 以本人推送。返回 {token, user}——token 即 Server token。"""
    aid = str(acct.get("id") or "")
    if not aid:
        raise HTTPException(502, "Console 返回了异常账号")
    db.upsert_external_user(aid, str(acct.get("name", "")), str(acct.get("plan", "体验版")))
    effective_expiry = db.cache_token(token, aid, expires_at)
    db.set_server_identity(aid, token)
    user = db.get_user(aid)
    assert user is not None  # 刚 upsert，必存在
    return {"token": token, "expires_at": effective_expiry, "user": _user_view(user)}


@router.post("/register")
def register(body: RegisterBody) -> dict:
    name = (body.name or "").strip()
    if not name or not body.password:
        raise HTTPException(400, "用户名和密码必填")
    if len(body.password) < 4:
        raise HTTPException(400, "密码至少 4 位")
    if not server_client.server_enabled():
        raise HTTPException(503, "AgentMate Server 未配置，无法注册账号")
    status, data = server_client.server_login_ex(name, body.password, register=True)
    if status == "ok" and data:
        return _mirror_server_account(
            data["token"], data.get("account") or {}, data.get("expires_at")
        )
    if status == "rejected":
        code = (data or {}).get("code", 400)
        detail = (data or {}).get("detail") or ("该用户名已被占用" if code == 409 else "注册失败")
        raise HTTPException(code if code in (400, 409) else 400, detail)
    raise HTTPException(503, "AgentMate Server 暂不可达，无法注册（请稍后重试）")


@router.post("/login")
def login(body: LoginBody) -> dict:
    name = (body.name or "").strip()
    if not server_client.server_enabled():
        raise HTTPException(503, "AgentMate Server 未配置，无法登录账号")
    status, data = server_client.server_login_ex(name, body.password, register=False)
    if status == "ok" and data:
        return _mirror_server_account(
            data["token"], data.get("account") or {}, data.get("expires_at")
        )
    if status == "rejected":
        raise HTTPException(401, "用户名或密码错误")
    raise HTTPException(503, "AgentMate Server 暂不可达，无法重新登录；已登录会话仍可离线使用")


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    token = (
        authorization[7:].strip()
        if authorization and authorization[:7].lower() == "bearer "
        else ""
    )
    if not token:
        return {"ok": True, "revoked_remote": False, "pending": False}

    # 先持久化撤销意图并清本地身份，保证断网或进程随后退出也不会在本机恢复登录态。
    db.enqueue_token_revocation(token)
    db.delete_token(token)
    db.clear_server_identity_by_token(token)
    revoked_remote = server_client.server_logout(token)
    if revoked_remote:
        db.mark_token_revoked(token)
    else:
        db.bump_token_revocation_tries(token)
    return {"ok": True, "revoked_remote": revoked_remote, "pending": not revoked_remote}
