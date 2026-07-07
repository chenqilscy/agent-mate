"""目录（WB-061 预埋，供 P3 下发）。Hub 侧同构表 catalog_items 的最小读端点；
builtin 全账号可读。完整下发/org 维护是 P3（WB-063）。"""
from __future__ import annotations

from fastapi import APIRouter

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog/{category}")
def list_catalog(category: str, account: Account = CurrentAccount) -> dict:
    return {"category": category, "items": db.list_catalog_items(category, scope="builtin")}
