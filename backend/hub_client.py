"""本地 backend 作为 WorkBuddy Hub 客户端（WB-062）。

所有调用 **guarded**：未接 Hub（HUB_URL 空）/ 不可达 / 非 200 → 返回 None，**从不抛异常**，
保证离线/未登录纯本地照跑（架构设计 §6「回退优先」）。这些是**同步阻塞**调用（httpx.get）——
调用方必须在工作线程里跑它，别占事件循环（WB-002 教训）。同步 payload 绝不含 LLM 凭据 /
连接器 secret / 沙箱工作区文件（铁律 4/11）。
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import settings

_TIMEOUT = 5.0


def hub_enabled() -> bool:
    return bool(settings.HUB_URL)


def _get(path: str, token: str) -> Optional[Any]:
    """带 token GET Hub 的 `path`，返回解析后的 JSON 或 None（guarded，从不抛）。"""
    if not token or not settings.HUB_URL:
        return None
    try:
        r = httpx.get(
            f"{settings.HUB_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001 —— 网络/解析任何错都当「未接/不可达」，回退本地
        return None


def verify_token(token: str) -> Optional[dict[str, Any]]:
    """Hub token → account dict（`{id,name,plan,...}`）或 None（未接 / 不可达 / 无效）。"""
    d = _get("/api/auth/verify", token)
    acct = d.get("account") if isinstance(d, dict) else None
    return acct if isinstance(acct, dict) else None


def list_projects(token: str) -> Optional[list[dict[str, Any]]]:
    """该账号在 Hub 的项目（owner + 成员），或 None（未接/不可达）。WB-062 Phase 2 下行 pull。"""
    d = _get("/api/projects", token)
    projs = d.get("projects") if isinstance(d, dict) else None
    return projs if isinstance(projs, list) else None


def list_project_members(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/members", token)
    mem = d.get("members") if isinstance(d, dict) else None
    return mem if isinstance(mem, list) else None


def post_timeline(token: str, project_id: str, event: dict[str, Any]) -> bool:
    """把一条时间线事件推给 Hub（WB-062 Phase 3）。成功(200) → True；未接/不可达/非 200 → False
    （outbox 保留待补推）。event 只含元数据（title/summary/ext_id），绝无凭据/工作区文件。"""
    if not token or not settings.HUB_URL:
        return False
    try:
        r = httpx.post(
            f"{settings.HUB_URL}/api/projects/{project_id}/timeline",
            headers={"Authorization": f"Bearer {token}"},
            json=event, timeout=_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:  # noqa: BLE001 —— 网络任何错都当失败，outbox 下轮再推
        return False


def create_project(token: str, project: dict[str, Any]) -> Optional[str]:
    """在 Hub 新建一个项目（WB-063 存量导入用），返回其 Hub id 或 None。
    project 只带元数据（name/instruction/loadout），无凭据/工作区文件。"""
    if not token or not settings.HUB_URL:
        return None
    try:
        r = httpx.post(
            f"{settings.HUB_URL}/api/projects",
            headers={"Authorization": f"Bearer {token}"},
            json=project, timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")
    except Exception:  # noqa: BLE001
        return None


def list_catalog(token: str, category: str) -> Optional[list[dict[str, Any]]]:
    """拉 Hub 侧目录（WB-063 目录下发）。Hub 预埋目录为空时返回 []，本地 builtin 种子仍作离线兜底。"""
    d = _get(f"/api/catalog/{category}", token)
    items = d.get("items") if isinstance(d, dict) else None
    return items if isinstance(items, list) else None
