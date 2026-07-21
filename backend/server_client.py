"""本地 backend 作为 AgentMate Server 客户端（WB-062）。

所有调用 **guarded**：未接 Server（AGENTMATE_SERVER_URL 空）/ 不可达 / 非 200 → 返回 None，**从不抛异常**，
保证离线/未登录纯本地照跑（架构设计 §6「回退优先」）。这些是**同步阻塞**调用（httpx.get）——
调用方必须在工作线程里跑它，别占事件循环（WB-002 教训）。同步 payload 绝不含 LLM 凭据 /
连接器 secret / 沙箱工作区文件（铁律 4/11）。
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import settings

_TIMEOUT = 5.0


def server_enabled() -> bool:
    return bool(settings.AGENTMATE_SERVER_URL)


def _get(path: str, token: str) -> Optional[Any]:
    """带 token GET Server 的 `path`，返回解析后的 JSON 或 None（guarded，从不抛）。"""
    if not token or not settings.AGENTMATE_SERVER_URL:
        return None
    try:
        r = httpx.get(
            f"{settings.AGENTMATE_SERVER_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001 —— 网络/解析任何错都当「未接/不可达」，回退本地
        return None


def verify_token(token: str) -> Optional[dict[str, Any]]:
    """Server token → account dict（`{id,name,plan,...}`）或 None（未接 / 不可达 / 无效）。"""
    d = _get("/api/auth/verify", token)
    acct = d.get("account") if isinstance(d, dict) else None
    return acct if isinstance(acct, dict) else None


def _post(path: str, token: str, body: Optional[dict] = None) -> Optional[Any]:
    """带 token POST Server 的 `path`，返回解析后的 JSON 或 None（guarded，从不抛）。"""
    if not settings.AGENTMATE_SERVER_URL:
        return None
    try:
        r = httpx.post(
            f"{settings.AGENTMATE_SERVER_URL}{path}",
            headers=({"Authorization": f"Bearer {token}"} if token else {}),
            json=body or {}, timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def _patch(path: str, token: str, body: Optional[dict] = None) -> Optional[Any]:
    """带 token PATCH Server 的 `path`（guarded，从不抛）。"""
    if not token or not settings.AGENTMATE_SERVER_URL:
        return None
    try:
        r = httpx.patch(
            f"{settings.AGENTMATE_SERVER_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=body or {}, timeout=_TIMEOUT,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _delete(path: str, token: str) -> bool:
    """带 token DELETE Server 的 `path`（guarded，从不抛）。成功(200)→True。"""
    if not token or not settings.AGENTMATE_SERVER_URL:
        return False
    try:
        r = httpx.delete(f"{settings.AGENTMATE_SERVER_URL}{path}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# ---- 前端接 Server 的代理（WB-067）：本地 backend 转发 Server 协作/登录，前端只连本地 ----

def server_login(name: str, password: str, register: bool = False) -> Optional[dict[str, Any]]:
    """代理登录/注册到 Server → {token, account}，或 None（未接/失败）。登录本身不带 token。"""
    return _post("/api/auth/register" if register else "/api/auth/login", "", {"name": name, "password": password})


def server_login_ex(name: str, password: str, register: bool = False) -> tuple[str, Optional[dict[str, Any]]]:
    """判别式登录/注册（WB-164）：区分 Console 的**明确拒绝**与**不可达**，让调用方能
    「Server 权威 + 离线兜底」——rejected 时不回退（避免密码错被本地放行），unreachable 时才回退。

    返回 `(status, payload)`：
      - `("ok", {token, account})` —— Console 200 通过；
      - `("rejected", {"code": <4xx>, "detail": <消息>})` —— Console 明确拒绝（401 密码错 / 409 重名 / 400）；
      - `("unreachable", None)` —— 未接 Server / 网络错 / 超时 / 5xx（本地应回退或诚实报错）。
    绝不抛异常。"""
    if not settings.AGENTMATE_SERVER_URL:
        return ("unreachable", None)
    path = "/api/auth/register" if register else "/api/auth/login"
    try:
        r = httpx.post(f"{settings.AGENTMATE_SERVER_URL}{path}", json={"name": name, "password": password}, timeout=_TIMEOUT)
    except Exception:  # noqa: BLE001 —— 网络/超时任何错都当不可达 → 兜底
        return ("unreachable", None)
    if r.status_code == 200:
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            return ("unreachable", None)
        return ("ok", data) if isinstance(data, dict) and data.get("token") else ("unreachable", None)
    if 400 <= r.status_code < 500:
        detail = ""
        try:
            body = r.json()
            detail = body.get("detail", "") if isinstance(body, dict) else ""
        except Exception:  # noqa: BLE001
            detail = ""
        return ("rejected", {"code": r.status_code, "detail": detail if isinstance(detail, str) else ""})
    return ("unreachable", None)  # 5xx 等 → 当 Console 暂时不可达


def list_comments(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/comments", token)
    c = d.get("comments") if isinstance(d, dict) else None
    return c if isinstance(c, list) else None


def post_comment(token: str, project_id: str, body: str) -> Optional[dict[str, Any]]:
    return _post(f"/api/projects/{project_id}/comments", token, {"body": body})


def list_item_comments(token: str, project_id: str, wid: str) -> Optional[list[dict[str, Any]]]:
    """任务级评论（WB-118）：拉 Server `work-items/{wid}/comments`。"""
    d = _get(f"/api/projects/{project_id}/work-items/{wid}/comments", token)
    c = d.get("comments") if isinstance(d, dict) else None
    return c if isinstance(c, list) else None


def post_item_comment(token: str, project_id: str, wid: str, body: str) -> Optional[dict[str, Any]]:
    return _post(f"/api/projects/{project_id}/work-items/{wid}/comments", token, {"body": body})


def list_presence(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/presence", token)
    p = d.get("presence") if isinstance(d, dict) else None
    return p if isinstance(p, list) else None


def server_notifications(token: str) -> Optional[dict[str, Any]]:
    d = _get("/api/notifications", token)
    return d if isinstance(d, dict) else None


def mark_server_notifications(token: str, ids: Optional[list[str]] = None) -> bool:
    return _post("/api/notifications/read", token, {"ids": ids} if ids else {}) is not None


def list_projects(token: str) -> Optional[list[dict[str, Any]]]:
    """该账号在 Server 的项目（owner + 成员），或 None（未接/不可达）。WB-062 Phase 2 下行 pull。"""
    d = _get("/api/projects", token)
    projs = d.get("projects") if isinstance(d, dict) else None
    return projs if isinstance(projs, list) else None


def list_project_members(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/members", token)
    mem = d.get("members") if isinstance(d, dict) else None
    return mem if isinstance(mem, list) else None


def post_timeline(token: str, project_id: str, event: dict[str, Any]) -> bool:
    """把一条时间线事件推给 Server（WB-062 Phase 3）。成功(200) → True；未接/不可达/非 200 → False
    （outbox 保留待补推）。event 只含元数据（title/summary/ext_id），绝无凭据/工作区文件。"""
    if not token or not settings.AGENTMATE_SERVER_URL:
        return False
    try:
        r = httpx.post(
            f"{settings.AGENTMATE_SERVER_URL}/api/projects/{project_id}/timeline",
            headers={"Authorization": f"Bearer {token}"},
            json=event, timeout=_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:  # noqa: BLE001 —— 网络任何错都当失败，outbox 下轮再推
        return False


def create_project(token: str, project: dict[str, Any]) -> Optional[str]:
    """在 Server 新建一个项目（WB-063 存量导入用），返回其 Server id 或 None。
    project 只带元数据（name/instruction/loadout），无凭据/工作区文件。"""
    if not token or not settings.AGENTMATE_SERVER_URL:
        return None
    try:
        r = httpx.post(
            f"{settings.AGENTMATE_SERVER_URL}/api/projects",
            headers={"Authorization": f"Bearer {token}"},
            json=project, timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")
    except Exception:  # noqa: BLE001
        return None


def list_catalog(token: str, category: str) -> Optional[list[dict[str, Any]]]:
    """拉 Server 侧目录（WB-063 目录下发）。Server 预埋目录为空时返回 []，本地 builtin 种子仍作离线兜底。"""
    d = _get(f"/api/catalog/{category}", token)
    items = d.get("items") if isinstance(d, dict) else None
    return items if isinstance(items, list) else None


def list_all_catalog(token: str) -> Optional[list[dict[str, Any]]]:
    """一次拉 Server 全量 builtin 目录（跨 category），供本地下发覆盖（WB-066）。
    None = 不可达（本地保留上次下发）；[] = Server 空（本地回落 builtin 兜底）。"""
    d = _get("/api/catalog", token)
    items = d.get("items") if isinstance(d, dict) else None
    return items if isinstance(items, list) else None


def pull_catalog_snapshot(token: str, capability: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Conditional catalog pull with non-sensitive App capability metadata."""
    result = _post("/api/catalog/pull", token, capability)
    return result if isinstance(result, dict) and isinstance(result.get("items"), list) else None


def record_skill_release_metric(token: str, release_id: str, event: str) -> bool:
    """Best-effort non-sensitive Skill release telemetry; offline never blocks local execution."""
    if not release_id:
        return False
    result = _post(f"/api/catalog/skill-releases/{release_id}/metrics", token, {"event": event})
    return isinstance(result, dict) and isinstance(result.get("metrics"), dict)


# ---- 团队计划/任务 work_items 代理（WB-091）：server-origin 项目的看板走 Server 权威 ----

def list_work_items(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    """拉 Server 项目的 work_items，或 None（未接/不可达）→ 调用方回退本地镜像。"""
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


# ---- 里程碑 milestones 代理（WB-108）：server-origin 项目的里程碑走 Server 权威 ----

def list_milestones(token: str, project_id: str) -> Optional[list[dict[str, Any]]]:
    d = _get(f"/api/projects/{project_id}/milestones", token)
    items = d.get("milestones") if isinstance(d, dict) else None
    return items if isinstance(items, list) else None


def create_milestone(token: str, project_id: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    d = _post(f"/api/projects/{project_id}/milestones", token, body)
    return d if isinstance(d, dict) else None


def update_milestone(token: str, project_id: str, mid: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    d = _patch(f"/api/projects/{project_id}/milestones/{mid}", token, body)
    return d if isinstance(d, dict) else None


def delete_milestone(token: str, project_id: str, mid: str) -> bool:
    return _delete(f"/api/projects/{project_id}/milestones/{mid}", token)


# ---- 项目配置 / 成员写代理（WB-112c）：server-origin 项目的成员·角色·配置以 Console 为权威 ----
# 只写协作元数据（名/角色/指令/loadout 名字数组），绝无凭据/工作区文件（红线 1/2）。

def get_project(token: str, project_id: str) -> Optional[dict[str, Any]]:
    """拉 Console 单个项目（含 role），或 None（未接/不可达）。"""
    d = _get(f"/api/projects/{project_id}", token)
    return d if isinstance(d, dict) else None


def update_project(token: str, project_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    """代理项目配置更新（name/instruction/connectors/experts/skills）到 Console。"""
    d = _patch(f"/api/projects/{project_id}", token, patch)
    return d if isinstance(d, dict) else None


def add_member(token: str, project_id: str, name: str, role: str) -> Optional[dict[str, Any]]:
    """按账号名加成员到 Console 项目（Console 侧按名解析 account）。返回结果 dict 或 None。"""
    d = _post(f"/api/projects/{project_id}/members", token, {"name": name, "role": role})
    return d if isinstance(d, dict) else None


def update_member(token: str, project_id: str, account_id: str, role: str) -> Optional[dict[str, Any]]:
    d = _patch(f"/api/projects/{project_id}/members/{account_id}", token, {"role": role})
    return d if isinstance(d, dict) else None


def remove_member(token: str, project_id: str, account_id: str) -> bool:
    return _delete(f"/api/projects/{project_id}/members/{account_id}", token)
