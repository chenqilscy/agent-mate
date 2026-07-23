"""Auth dependency (M7 C1: real accounts on a shared backend).

`current_user()` resolves the request's Bearer token to a Server-sourced account,
set per request by the ASGI AuthMiddleware into a contextvar. No token uses the
fixed ``LOCAL_USER`` row only as an anonymous guest scope so local execution can
work before login; it is not an AgentMate account source.
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import Depends

import server_client
from storage import db
from storage.models import LOCAL_USER_ID, User

# Set by AuthMiddleware for the duration of each request (None → anonymous guest scope).
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def resolve_token_to_user_id(token: str | None) -> str | None:
    """本地缓存解析：Bearer token → Server account id，或 None（→ 匿名访客作用域）。
    同步、快（只查本地 auth_tokens，含此前镜像过的 Server token）。Server 校验走 resolve_via_server。"""
    if not token:
        return None
    user_id = db.user_id_for_token(token)
    if not user_id:
        return None
    # 历史版本会签发本地账号 token。只有 Server 验证后同时写入
    # server_identities 的 token 才能恢复账号身份；旧本地 token 降级为访客。
    return user_id if db.get_server_identity(user_id) == token else None


def resolve_via_server(token: str) -> str | None:
    """本地未命中的 token：问 Server 校验（WB-062）。命中则把账号镜像进本地 users + 缓存 token，
    返回其 id；Server 关 / 不可达 / 无效 → None（→ 匿名访客作用域）。
    **阻塞调用**——中间件在工作线程里跑它，不占事件循环（WB-002）。"""
    acct = server_client.verify_token(token)
    if not acct or not acct.get("id"):
        return None
    aid = str(acct["id"])
    db.upsert_external_user(aid, str(acct.get("name", "")), str(acct.get("plan", "体验版")))
    db.cache_token(token, aid)
    db.set_server_identity(aid, token)  # 记住 Server token，供后台 outbox worker 以本人身份推送（Phase 3）
    return aid


def set_current_user_id(user_id: str | None) -> None:
    _current_user_id.set(user_id)


def current_user() -> User:
    uid = _current_user_id.get() or LOCAL_USER_ID
    user = db.get_user(uid)
    if user is None:
        # Token pointed at a since-deleted user, or the DB wasn't initialised yet.
        db.init_db()
        user = db.get_user(LOCAL_USER_ID)
    assert user is not None
    return user


CurrentUser = Depends(current_user)
