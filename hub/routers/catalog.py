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
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["catalog"])


def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


@router.get("/catalog")
def list_all_catalog(account: Account = CurrentAccount) -> dict:
    """所有 builtin 目录项（跨 category），供客户端一次性下行覆盖本地。"""
    return {"items": db.list_all_catalog_items(scope="builtin")}


@router.get("/catalog/{category}")
def list_catalog(category: str, account: Account = CurrentAccount) -> dict:
    return {"category": category, "items": db.list_catalog_items(category, scope="builtin")}


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
