"""Accounts / auth (M7 C1 + WB-164). Register + login return a Bearer token the
frontend sends on every request; the AuthMiddleware resolves it to the current
user. No token → the fixed local owner, so nothing breaks without logging in.

WB-164 —— **Server 权威 + 离线兜底**：接了 Server（AGENTMATE_SERVER_URL 设了）时，登录/注册以
Server 账号库为准，App token 即 Server token（校验后镜像进本地 users）。这样在 Console
建的账号能登 App、在 App 注册的账号 Console 也能看到——两端用户打通。Server 不可达时：
登录回退本地 users（离线/单机仍可登），注册诚实报 503（不静默建分裂的本地账号，遵循 WB-158）。
未接 Server（AGENTMATE_SERVER_URL 空）→ 完全走本地路径，纯本地零变化（离线优先）。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import server_client
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    name: str
    password: str


class LoginBody(BaseModel):
    name: str
    password: str


def _user_view(user) -> dict:
    return {"id": user.id, "name": user.name, "role": user.role.value, "plan": user.plan}


def _mirror_server_account(token: str, acct: dict) -> dict:
    """把 Console 校验过的账号镜像进本地 users + 缓存 Server token（后续请求本地命中，不再打 Console），
    并记住 Server 身份供后台 outbox 以本人推送。返回 {token, user}——token 即 Server token。"""
    aid = str(acct.get("id") or "")
    if not aid:
        raise HTTPException(502, "Console 返回了异常账号")
    db.upsert_external_user(aid, str(acct.get("name", "")), str(acct.get("plan", "体验版")))
    db.cache_token(token, aid)
    db.set_server_identity(aid, token)
    user = db.get_user(aid)
    assert user is not None  # 刚 upsert，必存在
    return {"token": token, "user": _user_view(user)}


@router.post("/register")
def register(body: RegisterBody) -> dict:
    name = (body.name or "").strip()
    if not name or not body.password:
        raise HTTPException(400, "用户名和密码必填")
    if len(body.password) < 4:
        raise HTTPException(400, "密码至少 4 位")
    # 接了 Server → 以 Server 为权威源注册（WB-164）。拒绝(重名/非法)透传 4xx；不可达诚实 503。
    if server_client.server_enabled():
        status, data = server_client.server_login_ex(name, body.password, register=True)
        if status == "ok" and data:
            return _mirror_server_account(data["token"], data.get("account") or {})
        if status == "rejected":
            code = (data or {}).get("code", 400)
            detail = (data or {}).get("detail") or ("该用户名已被占用" if code == 409 else "注册失败")
            raise HTTPException(code if code in (400, 409) else 400, detail)
        raise HTTPException(503, "Console 暂不可达，无法注册（请稍后重试）")
    # 未接 Server → 纯本地注册（离线优先，零变化）。
    if db.get_user_by_name(name) is not None:
        raise HTTPException(409, "该用户名已被占用")
    user = db.create_user(name=name, password=body.password, role=Role.OWNER)
    return {"token": db.create_token(user.id), "user": _user_view(user)}


@router.post("/login")
def login(body: LoginBody) -> dict:
    name = (body.name or "").strip()
    # 接了 Server → 以 Server 为权威源验证（WB-164）。ok 用 Server token 镜像；rejected(密码错/无此账号)
    # 直接 401（不回退，避免本地放行错误密码）；unreachable 才回退本地 users（离线/单机可登）。
    if server_client.server_enabled():
        status, data = server_client.server_login_ex(name, body.password, register=False)
        if status == "ok" and data:
            return _mirror_server_account(data["token"], data.get("account") or {})
        if status == "rejected":
            raise HTTPException(401, "用户名或密码错误")
        # unreachable → 落到下方本地兜底
    found = db.get_user_by_name(name)
    if found is None or not db.verify_password(body.password or "", found[1]):
        raise HTTPException(401, "用户名或密码错误")
    user = found[0]
    return {"token": db.create_token(user.id), "user": _user_view(user)}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization[:7].lower() == "bearer ":
        db.delete_token(authorization[7:].strip())
    return {"ok": True}
