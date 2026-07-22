"""Device-wide runtime settings exposed through the local backend (WB-291)."""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import device_settings
from auth.deps import current_user
from config import settings
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api/settings/runtime", tags=["settings"])


def _owner():
    user = current_user()
    if user.role not in (Role.OWNER, Role.ADMIN):
        raise HTTPException(403, "device owner only")
    return user


class UpdateBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list, max_length=100)


class TestBody(BaseModel):
    group: str = Field(min_length=1, max_length=60)


def _payload() -> dict[str, Any]:
    return {
        "items": device_settings.public_registry(),
        "deployment_only": sorted(device_settings.DEPLOYMENT_ONLY_KEYS),
        "audit": db.list_device_settings_audit(),
    }


@router.get("")
def get_runtime_settings() -> dict[str, Any]:
    _owner()
    return _payload()


@router.put("")
def put_runtime_settings(body: UpdateBody) -> dict[str, Any]:
    user = _owner()
    overlap = set(body.values) & set(body.clear)
    if overlap:
        raise HTTPException(400, f"同一设置不能同时保存和清除：{', '.join(sorted(overlap))}")
    if not body.values and not body.clear:
        raise HTTPException(400, "没有要保存的设置。")
    try:
        for key, value in body.values.items():
            device_settings.validate(key, value)
        for key in body.clear:
            device_settings.definition(key)
        for key, value in body.values.items():
            device_settings.set_value(key, value, actor_id=user.id)
        for key in body.clear:
            device_settings.clear_value(key, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    changed = set(body.values) | set(body.clear)
    device_settings.apply_all(changed_keys=changed)
    return _payload()


@router.post("/test")
def test_runtime_settings(body: TestBody) -> dict[str, Any]:
    _owner()
    if body.group == "voice":
        from routers import asr
        status = asr.status()
        return {"ok": bool(status.get("available")), **status}
    if body.group == "collaboration":
        if not settings.AGENTMATE_SERVER_URL:
            return {"ok": False, "error": "未配置 AgentMate Server 地址。"}
        try:
            response = httpx.get(f"{settings.AGENTMATE_SERVER_URL}/api/health", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"Server 连接失败：{exc}"}
        return {"ok": True, "service": response.json().get("service", "server")}
    if body.group == "observability":
        if not settings.langfuse_configured:
            return {"ok": False, "error": "Langfuse 配置不完整或尚未启用。"}
        client = None
        try:
            from langfuse import Langfuse
            client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                base_url=settings.LANGFUSE_BASE_URL,
                environment=settings.LANGFUSE_TRACING_ENVIRONMENT,
                tracing_enabled=False,
            )
            ok = bool(client.auth_check())
            return {"ok": ok, "error": "" if ok else "Langfuse 凭据校验失败。"}
        except Exception as exc:  # noqa: BLE001 - explicit connection test
            return {"ok": False, "error": f"Langfuse 连接失败：{type(exc).__name__}"}
        finally:
            if client is not None:
                try:
                    client.shutdown()
                except Exception:
                    pass
    raise HTTPException(400, f"设置组不支持连接测试：{body.group}")
