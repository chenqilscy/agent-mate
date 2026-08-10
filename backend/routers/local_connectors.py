"""Owner-scoped Local Agent MCP connector management (WB-476)."""
from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

import local_agent_store
from agent import mcp_client
from auth.deps import current_user


router = APIRouter(prefix="/api/connectors/local", tags=["connectors"])
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,119}$")


class ConnectorBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transport: str = Field(pattern=r"^(stdio|sse)$")
    command: str = Field(default="", max_length=1000)
    args: list[str] = Field(default_factory=list, max_length=100)
    url: str = Field(default="", max_length=4000)
    environment: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    secret_keys: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_transport(self):
        self.name = self.name.strip()
        self.command = self.command.strip()
        self.url = self.url.strip()
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio 连接器必须配置启动命令")
        if self.transport == "sse":
            parsed = urlparse(self.url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("SSE 连接器必须配置有效的 http(s) 地址")
        keys = list(dict.fromkeys([*self.secret_keys, *self.secrets.keys()]))
        if any(not _KEY.fullmatch(key) for key in [*self.environment, *keys]):
            raise ValueError("环境变量、Header 和凭据名称格式无效")
        if len(self.environment) > 100 or any(len(str(value)) > 8000 for value in self.environment.values()):
            raise ValueError("环境变量数量或长度超限")
        if any(len(value) > 20000 for value in self.secrets.values()):
            raise ValueError("凭据长度超限")
        self.secret_keys = keys
        return self


class EnabledBody(BaseModel):
    enabled: bool


class BuiltinCredentialsBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list, max_length=50)


class TestByNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in item.items()
        if key not in {"owner_id"}
    }


def _payload(owner_id: str) -> dict[str, Any]:
    return {
        "instances": [_public(item) for item in local_agent_store.list_connector_instances(owner_id)],
        "statuses": mcp_client.connector_statuses(owner_id),
    }


def _save(owner_id: str, instance_id: str, body: ConnectorBody) -> dict[str, Any]:
    previous = local_agent_store.get_connector_instance(owner_id, instance_id)
    try:
        item = local_agent_store.save_connector_instance(
            owner_id, instance_id=instance_id, name=body.name, transport=body.transport,
            command=body.command, args=body.args, url=body.url,
            environment=body.environment, secret_keys=body.secret_keys, enabled=body.enabled,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "连接器名称已存在") from exc
    for key in set(previous["secret_keys"] if previous else []) - set(body.secret_keys):
        local_agent_store.set_connector_secret(owner_id, instance_id, key, None)
    for key, value in body.secrets.items():
        if value:
            local_agent_store.set_connector_secret(owner_id, instance_id, key, value)
    return _public(local_agent_store.get_connector_instance(owner_id, instance_id) or item)


@router.get("")
def list_local_connectors() -> dict[str, Any]:
    return _payload(current_user().id)


@router.post("")
def create_local_connector(body: ConnectorBody) -> dict[str, Any]:
    owner_id = current_user().id
    return {"instance": _save(owner_id, str(uuid.uuid4()), body), **_payload(owner_id)}


@router.put("/{instance_id}")
def update_local_connector(instance_id: str, body: ConnectorBody) -> dict[str, Any]:
    owner_id = current_user().id
    if local_agent_store.get_connector_instance(owner_id, instance_id) is None:
        raise HTTPException(404, "连接器不存在")
    return {"instance": _save(owner_id, instance_id, body), **_payload(owner_id)}


@router.post("/{instance_id}/enabled")
def set_local_connector_enabled(instance_id: str, body: EnabledBody) -> dict[str, Any]:
    owner_id = current_user().id
    item = local_agent_store.get_connector_instance(owner_id, instance_id)
    if item is None:
        raise HTTPException(404, "连接器不存在")
    item = local_agent_store.save_connector_instance(
        owner_id, instance_id=instance_id, name=item["name"], transport=item["transport"],
        command=item["command"], args=item["args"], url=item["url"],
        environment=item["environment"], secret_keys=item["secret_keys"], enabled=body.enabled,
    )
    return {"instance": _public(item), **_payload(owner_id)}


async def _test(owner_id: str, name: str, instance_id: str = "") -> dict[str, Any]:
    tools, stack, skipped = await mcp_client.open_connectors(
        [name], owner_id=owner_id, allow_unhealthy=True,
    )
    try:
        error = skipped[0]["reason"] if skipped else ""
        ok = bool(tools) and not error
        if instance_id:
            local_agent_store.set_connector_health(
                owner_id, instance_id, status="healthy" if ok else "unhealthy",
                error=error or ("未发现 MCP 工具" if not tools else ""), tool_count=len(tools),
            )
        return {
            "ok": ok, "name": name,
            "tools": [{"name": tool.orig, "description": tool.description} for tool in tools],
            "error": error or ("" if tools else "未发现 MCP 工具"),
        }
    finally:
        await stack.aclose()


@router.post("/{instance_id}/test")
async def test_local_connector(instance_id: str) -> dict[str, Any]:
    owner_id = current_user().id
    item = local_agent_store.get_connector_instance(owner_id, instance_id)
    if item is None:
        raise HTTPException(404, "连接器不存在")
    return await _test(owner_id, item["name"], instance_id)


@router.post("/test-by-name")
async def test_connector_by_name(body: TestByNameBody) -> dict[str, Any]:
    owner_id = current_user().id
    if body.name not in mcp_client.connector_specs(owner_id):
        raise HTTPException(404, "连接器不存在或不可执行")
    instance = next((item for item in local_agent_store.list_connector_instances(owner_id) if item["name"] == body.name), None)
    return await _test(owner_id, body.name, str(instance["id"]) if instance else "")


@router.put("/builtins/{name}/credentials")
def set_builtin_credentials(name: str, body: BuiltinCredentialsBody) -> dict[str, Any]:
    owner_id = current_user().id
    specs = mcp_client.connector_specs()
    spec = specs.get(name)
    if spec is None:
        raise HTTPException(404, "内置连接器不存在")
    allowed = {str(item) for item in spec.get("requires", [])}
    if (set(body.values) | set(body.clear)) - allowed:
        raise HTTPException(400, "包含该连接器未声明的凭据名称")
    for key, value in body.values.items():
        local_agent_store.set_builtin_connector_secret(owner_id, name, key, value or None)
    for key in body.clear:
        local_agent_store.set_builtin_connector_secret(owner_id, name, key, None)
    return _payload(owner_id)


@router.delete("/{instance_id}")
def delete_local_connector(instance_id: str) -> dict[str, Any]:
    owner_id = current_user().id
    if not local_agent_store.delete_connector_instance(owner_id, instance_id):
        raise HTTPException(404, "连接器不存在")
    return _payload(owner_id)
