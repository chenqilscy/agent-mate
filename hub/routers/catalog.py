"""目录（WB-061 预埋 + WB-066 运营 Admin）。

`GET` 全账号可读（builtin 下发源）；写端点（POST/PATCH/DELETE）**仅平台管理员**（首个注册账号自举），
用于运营内置目录——增/改/删/排序一条 → 客户端 pull 后反映（本地 override 叠加、离线 builtin 兜底）。
org 级目录运营（团队 Admin）留后续。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import skillhub_client
import skillhub_sync
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["catalog"])


def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


# ── SkillHub 目录镜像 + 查询代理（WB-069）──────────────────────────────────
# 定时镜像的浏览目录仍走上面的 GET /api/catalog（category='skill' + 'skill-category' 骨架）。
# 这里加：管理员手动触发同步；实时查询统一经 Hub 代理（跑 CLI search）。


@router.post("/catalog/skills/sync")
def sync_skillhub(account: Account = CurrentAccount) -> dict:
    """手动触发一次 SkillHub 目录镜像同步（平台管理员）。返回条数/分类分布统计。"""
    _require_admin(account)
    return skillhub_sync.sync_once()


@router.get("/catalog/skills/search")
def search_skillhub(q: str = "", limit: int = 12, account: Account = CurrentAccount) -> dict:
    """Hub 统一查询代理：实时查 SkillHub（CLI search + 短缓存）。

    CLI 不可用/失败 → 空结果 + cli=false，客户端据此回退本地 backend 直连（离线兜底）。
    """
    return {"query": q, "results": skillhub_client.search(q, limit),
            "cli": skillhub_client.cli_available()}


@router.get("/catalog")
def list_all_catalog(all: bool = False, account: Account = CurrentAccount) -> dict:
    """所有 builtin 目录项（跨 category），供客户端一次性下行覆盖本地。
    `?all=true`（仅平台管理员）连停用项一并返回，供门户高级 JSON 视图。"""
    inc = all and account.is_platform_admin
    return {"items": db.list_all_catalog_items(scope="builtin", include_disabled=inc)}


@router.get("/catalog/{category}")
def list_catalog(category: str, all: bool = False, account: Account = CurrentAccount) -> dict:
    """某 category 目录项。`?all=true`（仅平台管理员）含停用项 + `enabled` 标志，供门户 CRUD 列表。"""
    inc = all and account.is_platform_admin
    return {"category": category, "items": db.list_catalog_items(category, scope="builtin", include_disabled=inc)}


class CatalogItemBody(BaseModel):
    category: str
    kind: str = ""
    data: Any = None  # 目录卡：数组(如 EXP_GRID 元组) 或对象(如 CONN_META)
    sort: int = 0


@router.post("/catalog")
def create_item(body: CatalogItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    iid = db.create_catalog_item(
        category=body.category, data=body.data, scope="builtin", kind=body.kind, sort=body.sort,
    )
    return {"id": iid}


class UpdateItemBody(BaseModel):
    data: Any = None
    sort: int | None = None
    enabled: bool | None = None


@router.patch("/catalog/item/{item_id}")
def update_item(item_id: str, body: UpdateItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if not db.update_catalog_item(item_id, data=body.data, sort=body.sort, enabled=body.enabled):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}


@router.delete("/catalog/item/{item_id}")
def delete_item(item_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if not db.delete_catalog_item(item_id):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}
