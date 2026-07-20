"""SkillHub 目录镜像同步（WB-069）。

定时把 SkillHub 榜单目录抓下来、按 12 场景分类归组、镜像进 Server `catalog_items`
（`scope=builtin`、`kind=skillhub`）。客户端 pull `/api/catalog` 即得镜像
（离线兜底 + 团队口径一致）。**安装动作永远留本地**；本模块只做「可浏览目录」的镜像。

分类骨架（12 类中文名/排序）来自 SkillHub `GET /api/v1/categories` 的真数据快照——
CLI 无 categories 命令，故以静态映射维护；日后要动态刷新可加一个直连 GET。

口径（WB-069 决策）：全量 = 6 榜单并集去重（`rankings --type all`，实测约 369 条、覆盖 12 类），
非严格 1:1 全量（公开 API 拿不到）。「分类 search 补量」为后续增强，本期不做。
"""
from __future__ import annotations

import asyncio
from typing import Any

import db
import skillhub_client
from config import settings

# SkillHub 一级分类（快照自 GET /api/v1/categories，2026-07-08）。key ⇄ 卡片 `category` 字段。
SCENE_CATEGORIES: list[dict[str, Any]] = [
    {"key": "office-efficiency", "name": "办公效率", "nameEn": "Office Efficiency", "sortOrder": 10},
    {"key": "content-creation", "name": "内容创作", "nameEn": "Content Creation", "sortOrder": 20},
    {"key": "dev-programming", "name": "开发编程", "nameEn": "Development", "sortOrder": 30},
    {"key": "data-analysis", "name": "数据分析", "nameEn": "Data Analysis", "sortOrder": 40},
    {"key": "design-media", "name": "设计多媒体", "nameEn": "Design & Media", "sortOrder": 50},
    {"key": "ai-agent", "name": "AI Agent", "nameEn": "AI Agent", "sortOrder": 60},
    {"key": "knowledge-management", "name": "知识管理", "nameEn": "Knowledge Management", "sortOrder": 70},
    {"key": "business-ops", "name": "商业运营", "nameEn": "Business Operations", "sortOrder": 80},
    {"key": "education", "name": "教育学习", "nameEn": "Education", "sortOrder": 90},
    {"key": "professional", "name": "行业专业", "nameEn": "Professional", "sortOrder": 100},
    {"key": "it-ops-security", "name": "IT 运维与安全", "nameEn": "IT Ops & Security", "sortOrder": 110},
    {"key": "life-service", "name": "生活服务", "nameEn": "Life Service", "sortOrder": 120},
]
_SCENE_BY_KEY = {c["key"]: c for c in SCENE_CATEGORIES}
_OTHER = {"key": "other", "name": "其他", "nameEn": "Other", "sortOrder": 999}


def _scene(card: dict[str, Any]) -> dict[str, Any]:
    return _SCENE_BY_KEY.get(str(card.get("category") or "").strip(), _OTHER)


def _score(card: dict[str, Any]) -> float:
    try:
        return float(card.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def sync_once() -> dict[str, Any]:
    """抓 SkillHub 榜单 → 归组 → 原子替换镜像。返回统计。

    取数主路径是直连公开 HTTP（WB-094），无需本机 CLI；故不再用 `cli_available()` 作前置
    （旧逻辑会让无 CLI 环境连手动同步都被拦下，WB-126）。抓空（站点不可达且 CLI 也不可用）
    → **不动库**（保留上次镜像，铁律：不造假、local-first 稳定）。
    """
    cards = skillhub_client.rankings_all()
    if not cards:
        return {"ok": False, "error": "SkillHub 无数据或抓取失败（保留上次镜像）", "total": 0}

    # 按场景 sortOrder 升序、类内按 score 降序，得到稳定顺序。
    ordered = sorted(cards, key=lambda c: (_scene(c)["sortOrder"], -_score(c)))
    by_cat: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(ordered):
        sc = _scene(c)
        by_cat[sc["key"]] = by_cat.get(sc["key"], 0) + 1
        data = {**c, "skillhub_category": sc["key"], "skillhub_category_name": sc["name"]}
        rows.append({"category": "skill", "kind": "skillhub", "data": data,
                     "sort": sc["sortOrder"] * 10000 + i})

    # 分类骨架行：完整 12 类 + 每类计数（前端可显示空分类），有归入「其他」时附加。
    taxonomy = [{**sc, "count": by_cat.get(sc["key"], 0)} for sc in SCENE_CATEGORIES]
    if by_cat.get("other"):
        taxonomy.append({**_OTHER, "count": by_cat["other"]})
    rows.append({"category": "skill-category", "kind": "skillhub-taxonomy",
                 "data": {"items": taxonomy}, "sort": 0})

    stats = db.replace_skillhub_mirror(rows)
    return {"ok": True, "total": len(cards), "by_category": by_cat, **stats}


async def run_periodic() -> None:
    """后台循环：启动先跑一次，之后按 `SKILLHUB_SYNC_INTERVAL` 周期跑。0 = 不启动。"""
    interval = settings.SKILLHUB_SYNC_INTERVAL
    if interval <= 0:
        return
    while True:
        try:
            await asyncio.to_thread(sync_once)
        except Exception:  # noqa: BLE001 — 后台任务不因单次异常退出
            pass
        await asyncio.sleep(interval)
