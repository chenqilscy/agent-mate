"""Hub 同步端点（WB-062）。客户端用其 Hub token 触发下行 pull（项目/成员镜像）。

同步 def 路由 → FastAPI 自动在线程池里跑，故内部的阻塞 Hub 调用不占事件循环。
未接 Hub（HUB_URL 空）→ 直接返回 hub:false，纯本地照旧。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

import hub_client
import hub_sync
from storage import db
from storage.models import LOCAL_USER_ID

router = APIRouter(prefix="/api", tags=["hub"])


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


@router.post("/hub/pull")
def hub_pull(authorization: str = Header(default="")) -> dict:
    if not hub_client.hub_enabled():
        return {"hub": False, "synced": 0, "projects": []}
    token = authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""
    result = hub_sync.pull(token)                 # 下行：拉项目/成员镜像
    flushed = hub_sync.flush_outbox()             # 上行：顺手补推 outbox（同步路由=线程池）
    return {"hub": True, **result, "flushed": flushed.get("pushed", 0)}


@router.post("/hub/import")
def hub_import(authorization: str = Header(default="")) -> dict:
    """存量导入（WB-063）：把本机 LOCAL_USER 的本地原生项目上行到 Hub，幂等。需带有效 Hub token。"""
    if not hub_client.hub_enabled():
        return {"hub": False, "imported": 0, "skipped": 0}
    acct = hub_client.verify_token(_bearer(authorization))
    if not acct:
        raise HTTPException(401, "invalid or missing hub token")
    return hub_sync.import_local_to_hub(_bearer(authorization), acct)


@router.get("/hub/status")
def hub_status() -> dict:
    """本地是否已接 Hub、是否已绑定某 Hub 账号（前端据此显示同步/导入入口）。
    未接 Hub → enabled False，纯本地照旧——前端不应因此禁用任何本地功能。"""
    link = db.get_hub_link(LOCAL_USER_ID)
    return {
        "enabled": hub_client.hub_enabled(),
        "linked": {"account_id": link["hub_account_id"], "name": link["hub_account_name"]} if link else None,
    }
