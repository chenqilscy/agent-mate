"""Catalog — 橱窗目录（WB-060）。把原 data/catalog.ts 的静态商品卡从 DB 供给前端。

只读浏览内容、无 owner 维度（builtin 目录，全用户可见）；前端 catalogStore 消费、替代静态 import，
后端未连时前端仍有静态兜底。功能定义（专家人格 / 连接器 spec，WB-059）在各自路由，不在此。
"""
from __future__ import annotations

from fastapi import APIRouter

from storage import db

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/catalog")
def get_catalog() -> dict:
    """所有橱窗目录，按 export 名分组（EXP_GRID / EXP_TEAMS / CONNS / CONN_META / AUTO / INSP / …）。"""
    return db.showcase_all()
