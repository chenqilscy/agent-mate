"""Hub 同步端点（WB-062）。客户端用其 Hub token 触发下行 pull（项目/成员镜像）。

同步 def 路由 → FastAPI 自动在线程池里跑，故内部的阻塞 Hub 调用不占事件循环。
未接 Hub（HUB_URL 空）→ 直接返回 hub:false，纯本地照旧。
"""
from __future__ import annotations

from fastapi import APIRouter, Header

import hub_client
import hub_sync

router = APIRouter(prefix="/api", tags=["hub"])


@router.post("/hub/pull")
def hub_pull(authorization: str = Header(default="")) -> dict:
    if not hub_client.hub_enabled():
        return {"hub": False, "synced": 0, "projects": []}
    token = authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""
    return {"hub": True, **hub_sync.pull(token)}


@router.get("/hub/status")
def hub_status() -> dict:
    """本地是否已接 Hub（前端据此显示同步入口）。不泄露 Hub 地址细节以外的东西。"""
    return {"enabled": hub_client.hub_enabled()}
