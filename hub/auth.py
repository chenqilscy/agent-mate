"""Hub 鉴权依赖（WB-061）。

Hub 是中心服务，**强制鉴权**——无/错 token 一律 401（不同于本地 backend「无 token 退本地 owner」）。
`current_account` 把 Bearer token 解析为账号；受保护路由依赖它。
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

import db
from models import Account, Role


def bearer_token(authorization: str = Header(default="")) -> str:
    if authorization[:7].lower() == "bearer ":
        return authorization[7:].strip()
    return ""


def current_account(authorization: str = Header(default="")) -> Account:
    token = bearer_token(authorization)
    aid = db.account_id_for_token(token) if token else None
    acc = db.get_account(aid) if aid else None
    if acc is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    db.touch_last_seen(acc.id)  # WB-065 在线状态心跳：每个 authed 请求刷新 last_seen
    return acc


CurrentAccount = Depends(current_account)


# 成员角色只能是 Admin/Member/Viewer——Owner 是隐式的（由 owner_id 记），不可经成员接口赋予。
_ASSIGNABLE = {Role.ADMIN, Role.MEMBER, Role.VIEWER}


def parse_member_role(s: str) -> Role:
    try:
        role = Role(s)
    except ValueError as e:
        raise HTTPException(400, f"invalid role: {s}") from e
    if role not in _ASSIGNABLE:
        raise HTTPException(400, "role must be Admin / Member / Viewer")
    return role
