"""安全中心（WB-152）：命令安全策略（黑名单·真拦截）+ 审计日志。

owner 经 contextvar 传入工具执行线程（run_chat 设，asyncio.to_thread 复制 contextvar）。
只在 run_command 这一处做拦截 + 记录，fail-open（owner 未知则放行，不破坏工具执行）。
"""
from __future__ import annotations

import contextvars
import json

from storage import db

_KEY_CMD_BLOCKLIST = "security.cmd_blocklist"

# 当前工具执行归属的 owner（run_chat 设）。None → 放行且不审计（fail-open）。
_owner_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("security_owner", default=None)


def set_security_context(owner_id: str | None) -> None:
    _owner_ctx.set(owner_id)


def current_owner() -> str | None:
    return _owner_ctx.get()


# ---- 命令黑名单 ---------------------------------------------------------

def get_command_blocklist(owner_id: str) -> list[str]:
    raw = db.get_user_setting(owner_id, _KEY_CMD_BLOCKLIST)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def set_command_blocklist(owner_id: str, patterns: list[str]) -> list[str]:
    clean: list[str] = []
    for p in patterns or []:
        s = str(p).strip()[:200]
        if s and s not in clean:
            clean.append(s)
    clean = clean[:100]
    db.set_user_setting(owner_id, _KEY_CMD_BLOCKLIST, json.dumps(clean, ensure_ascii=False) if clean else None)
    return clean


def check_command(command: str, owner_id: str | None = None) -> tuple[bool, str]:
    """(allowed, matched_pattern)。命令（大小写不敏感）命中任一黑名单子串 → 拒绝。
    owner 未知 → 放行（fail-open）。"""
    owner = owner_id or current_owner()
    if not owner:
        return True, ""
    cmd = (command or "").lower()
    for pat in get_command_blocklist(owner):
        if pat and pat.lower() in cmd:
            return False, pat
    return True, ""


# ---- 审计 ---------------------------------------------------------------

def audit(owner_id: str | None, tool: str, detail: str, action: str = "executed") -> None:
    if not owner_id:
        return
    try:
        db.add_audit(owner_id, tool, detail, action)
    except Exception:  # noqa: BLE001 — 审计失败绝不影响工具执行
        pass
