"""本地 backend 作为 WorkBuddy Hub 客户端（WB-062）。

所有调用 **guarded**：未接 Hub（HUB_URL 空）/ 不可达 / 非 200 → 返回 None，**从不抛异常**，
保证离线/未登录纯本地照跑（架构设计 §6「回退优先」）。这些是**同步阻塞**调用（httpx.get）——
调用方必须在工作线程里跑它，别占事件循环（WB-002 教训）。同步 payload 绝不含 LLM 凭据 /
连接器 secret / 沙箱工作区文件（铁律 4/11）。
"""
from __future__ import annotations

import urllib.parse
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


def _post(path: str, token: str, body: Optional[dict] = None) -> Optional[Any]:
    """带 token POST Hub 的 `path`，返回解析后的 JSON 或 None（guarded，从不抛）。"""
    if not settings.HUB_URL:
        return None
    try:
        r = httpx.post(
            f"{settings.HUB_URL}{path}",
            headers=({"Authorization": f"Bearer {token}"} if token else {}),
            json=body or {}, timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def _patch(path: str, token: str, body: Optional[dict] = None) -> Optional[Any]:
    """带 token PATCH Hub 的 `path`（guarded，从不抛）。"""
    if not token or not settings.HUB_URL:
        return None
    try:
        r = httpx.patch(
            f"{settings.HUB_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=body or {}, timeout=_TIMEOUT,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _delete(path: str, token: str) -> bool:
    """带 token DELETE Hub 的 `path`（guarded，从不抛）。成功(200)→True。"""
    if not token or not settings.HUB_URL:
        return False
    try:
        r = httpx.delete(f"{settings.HUB_URL}{path}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# ---- 前端接 Hub 的代理（WB-067）：本地 backend 转发 Hub 协作/登录，前端只连本地 ----

def hub_login(name: str, password: str, register: bool = False) -> Optional[dict[str, Any]]:
    """代理登录/注册到 Hub → {token, account}，或 None（未接/失败）。登录本身不带 token。"""
    return _post("/api/auth/register" if register else "/api/auth/login", "", {"name": name, "password": password})


def list_comments(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/comments", token)
    c = d.get("comments") if isinstance(d, dict) else None
    return c if isinstance(c, list) else None


def post_comment(token: str, project_id: str, body: str) -> Optional[dict[str, Any]]:
    return _post(f"/api/projects/{project_id}/comments", token, {"body": body})


def list_presence(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/presence", token)
    p = d.get("presence") if isinstance(d, dict) else None
    return p if isinstance(p, list) else None


def hub_notifications(token: str) -> Optional[dict[str, Any]]:
    d = _get("/api/notifications", token)
    return d if isinstance(d, dict) else None


def mark_hub_notifications(token: str, ids: Optional[list[str]] = None) -> bool:
    return _post("/api/notifications/read", token, {"ids": ids} if ids else {}) is not None


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


def list_all_catalog(token: str) -> Optional[list[dict[str, Any]]]:
    """一次拉 Hub 全量 builtin 目录（跨 category），供本地下发覆盖（WB-066）。
    None = 不可达（本地保留上次下发）；[] = Hub 空（本地回落 builtin 兜底）。"""
    d = _get("/api/catalog", token)
    items = d.get("items") if isinstance(d, dict) else None
    return items if isinstance(items, list) else None


def search_skillhub(token: str, q: str, limit: int = 12) -> Optional[list[dict[str, Any]]]:
    """经 Hub 查询代理实时搜 SkillHub（WB-070）。None = 未接/不可达/无结果 → 调用方回退本地。"""
    qs = urllib.parse.urlencode({"q": q, "limit": limit})
    d = _get(f"/api/catalog/skills/search?{qs}", token)
    res = d.get("results") if isinstance(d, dict) else None
    return res if isinstance(res, list) and res else None


# ---- 团队计划/任务 work_items 代理（WB-091）：hub-origin 项目的看板走 Hub 权威 ----

def list_work_items(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    """拉 Hub 项目的 work_items，或 None（未接/不可达）→ 调用方回退本地镜像。"""
    d = _get(f"/api/projects/{project_id}/work-items", token)
    items = d.get("items") if isinstance(d, dict) else None
    return items if isinstance(items, list) else None


def create_work_item(token: str, project_id: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    d = _post(f"/api/projects/{project_id}/work-items", token, body)
    return d if isinstance(d, dict) else None


def update_work_item(token: str, project_id: str, wid: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    d = _patch(f"/api/projects/{project_id}/work-items/{wid}", token, body)
    return d if isinstance(d, dict) else None


def delete_work_item(token: str, project_id: str, wid: str) -> bool:
    return _delete(f"/api/projects/{project_id}/work-items/{wid}", token)
