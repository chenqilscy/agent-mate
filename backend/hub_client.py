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


def verify_token(token: str) -> Optional[dict[str, Any]]:
    """Hub token → account dict（`{id,name,plan,...}`）或 None（未接 / 不可达 / 无效）。"""
    if not token or not settings.HUB_URL:
        return None
    try:
        r = httpx.get(
            f"{settings.HUB_URL}/api/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        acct = r.json().get("account")
        return acct if isinstance(acct, dict) else None
    except Exception:  # noqa: BLE001 —— 网络/解析任何错都当「未接/不可达」，回退本地
        return None
