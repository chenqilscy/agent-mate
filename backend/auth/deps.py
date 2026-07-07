"""Auth dependency (M7 C1: real accounts on a shared backend).

`current_user()` resolves the request's Bearer token to a user, set per request by
the ASGI AuthMiddleware into a contextvar. No token → the fixed local owner, so
single-machine use keeps working without logging in. Routes never change — they
just call `current_user()` (decision A.3).
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import Depends

import hub_client
from storage import db
from storage.models import LOCAL_USER_ID, User

# Set by AuthMiddleware for the duration of each request (None → local owner).
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def resolve_token_to_user_id(token: str | None) -> str | None:
    """本地缓存解析：Bearer token → user id，或 None（→ 本地 owner 回退）。
    同步、快（只查本地 auth_tokens，含此前镜像过的 Hub token）。Hub 校验走 resolve_via_hub。"""
    return db.user_id_for_token(token) if token else None


def resolve_via_hub(token: str) -> str | None:
    """本地未命中的 token：问 Hub 校验（WB-062）。命中则把账号镜像进本地 users + 缓存 token，
    返回其 id；Hub 关 / 不可达 / 无效 → None（→ 本地 owner 回退，离线不受影响）。
    **阻塞调用**——中间件在工作线程里跑它，不占事件循环（WB-002）。"""
    acct = hub_client.verify_token(token)
    if not acct or not acct.get("id"):
        return None
    aid = str(acct["id"])
    db.upsert_external_user(aid, str(acct.get("name", "")), str(acct.get("plan", "体验版")))
    db.cache_token(token, aid)
    db.set_hub_identity(aid, token)  # 记住 Hub token，供后台 outbox worker 以本人身份推送（Phase 3）
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
