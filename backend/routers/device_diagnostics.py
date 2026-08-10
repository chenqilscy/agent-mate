"""Actionable Local Agent diagnostics exposed to the authenticated App (WB-477)."""
from __future__ import annotations

import os
import platform
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import device_settings
import local_agent_store
import run_transport
from agent import mcp_client, server_run_worker, worker_health
from auth.deps import current_user
from config import settings


router = APIRouter(prefix="/api/device-diagnostics", tags=["diagnostics"])


class ActionBody(BaseModel):
    action: str = Field(pattern=r"^(retry_transport|register_device|clear_completed)$")


def _snapshot(owner_id: str) -> dict[str, Any]:
    transport = local_agent_store.diagnostics_snapshot(owner_id)
    workers = worker_health.snapshot()
    server_runs = server_run_worker.snapshot(owner_id)
    connectors = mcp_client.connector_statuses(owner_id)
    now = time.time()
    issues: list[dict[str, Any]] = []
    if not settings.server_enabled:
        issues.append({"code": "server_not_configured", "severity": "error", "title": "未配置 AgentMate Server", "detail": "任务与 Run 无法进入 Server 控制平面。", "action": "runtime_settings"})
    if not transport["identity"]["bound"]:
        issues.append({"code": "identity_missing", "severity": "error", "title": "这台设备没有有效 Server 身份", "detail": "重新登录后，App 会把当前账号安全绑定到 Local Agent。", "action": "login"})
    wal = transport["wal"]
    if wal["count"]:
        age = max(0, int(now - wal["oldest_at"])) if wal["oldest_at"] else 0
        issues.append({
            "code": "wal_pending", "severity": "error" if age > 60 else "warning",
            "title": f"{wal['count']} 个执行事件待 Server 持久化回执",
            "detail": f"这是机器传输状态，不是用户确认；最旧事件已等待 {age} 秒，数据仍安全保存在本机 WAL。",
            "action": "retry_transport",
        })
    for lease in transport["leases"]:
        if lease["last_error"]:
            issues.append({
                "code": f"lease:{lease['run_id']}", "severity": "error",
                "title": "Run 传输被阻断", "detail": str(lease["last_error"]),
                "action": "open_run", "run_id": lease["run_id"],
            })
        elif lease["status"] == "active" and float(lease["expires_at"] or 0) <= now:
            issues.append({
                "code": f"lease_expired:{lease['run_id']}", "severity": "error",
                "title": "Run lease 已过期", "detail": "执行节点将在 Server 侧重新恢复或失败关闭。",
                "action": "open_run", "run_id": lease["run_id"],
            })
    for component in workers.get("components", []):
        if int(component.get("consecutive_failures") or 0) > 0:
            issues.append({
                "code": f"worker:{component['name']}", "severity": "error",
                "title": f"后台组件异常 · {component['name']}",
                "detail": str(component.get("last_error") or "后台循环失败"), "action": "recheck",
            })
    unhealthy = [item for item in connectors if item["enabled"] and not item["healthy"]]
    if unhealthy:
        issues.append({
            "code": "connectors_unhealthy", "severity": "warning",
            "title": f"{len(unhealthy)} 个连接器尚未就绪",
            "detail": "、".join(item["name"] for item in unhealthy[:8]), "action": "connectors",
        })
    return {
        "checked_at": now,
        "process": {
            "pid": os.getpid(), "platform": platform.system(), "release": platform.release(),
            "python": platform.python_version(), "server_configured": settings.server_enabled,
            "server_url": settings.AGENTMATE_SERVER_URL,
            "protocol_version": run_transport.PROTOCOL_VERSION,
        },
        "transport": transport, "workers": workers, "server_runs": server_runs,
        "connectors": connectors,
        "runtime": {"items": device_settings.public_registry()},
        "issues": issues,
        "healthy": not any(item["severity"] == "error" for item in issues),
    }


@router.get("")
def diagnostics() -> dict[str, Any]:
    return _snapshot(current_user().id)


@router.post("/actions")
def diagnostic_action(body: ActionBody) -> dict[str, Any]:
    owner_id = current_user().id
    result: dict[str, Any]
    if body.action in {"retry_transport", "register_device"}:
        user_token = local_agent_store.get_server_identity(owner_id)
        if not user_token:
            raise HTTPException(409, "设备没有有效 Server 身份，请重新登录")
        device_token = run_transport.ensure_device(owner_id, user_token)
        if not device_token:
            raise HTTPException(503, "设备注册失败，请检查 Server 连接")
        if body.action == "register_device":
            result = {"registered": True, "device_id": run_transport.device_id(owner_id)}
        else:
            if not run_transport.heartbeat(owner_id, device_token):
                raise HTTPException(503, "Server 心跳失败")
            result = run_transport.flush_wal(owner_id, device_token)
    elif body.action == "clear_completed":
        result = {"deleted": local_agent_store.clear_completed_transport(owner_id)}
    else:  # pragma: no cover - Pydantic rejects unsupported actions
        raise HTTPException(400, "不支持的诊断动作")
    return {"result": result, "diagnostics": _snapshot(owner_id)}
