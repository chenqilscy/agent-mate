"""目录（WB-061 预埋 + WB-066 运营 Admin）。

`GET` 全账号可读（builtin 下发源）；写端点（POST/PATCH/DELETE）**仅平台管理员**（首个注册账号自举），
用于运营内置目录——增/改/删/排序一条 → 客户端 pull 后反映（本地 override 叠加、离线 builtin 兜底）。
org 级目录运营（团队 Admin）留后续。
"""
from __future__ import annotations
import hashlib

import json
import re
import time
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["catalog"])
_SKILL_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PLACEMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_TOOL_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SHELL_PLATFORMS = {"windows", "linux", "macos"}
_MAX_TOOL_SCHEMA_BYTES = 32 * 1024
_MAX_TOOL_SCRIPT_BYTES = 128 * 1024
_BUILTIN_CONNECTOR_SERVERS = {"notes", "clock", "search", "telegram", "kdocs"}
_RECOMMENDATION_CATEGORIES = {
    "SKILL_RECOMMENDATIONS", "CONNECTOR_RECOMMENDATIONS", "EXPERT_RECOMMENDATIONS",
}
def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


def _downlink_catalog_items(*, include_all: bool = False, include_withdrawn: bool = False) -> list[dict[str, Any]]:
    items = db.list_all_catalog_items(scope="builtin", include_disabled=include_all)
    if not include_all:
        # A withdrawn Skill is an explicit state, not an omitted row.  Recommendations
        # use the same rule so an intentionally empty placement does not revive fallback.
        categories = set(_RECOMMENDATION_CATEGORIES)
        if include_withdrawn:
            categories.add("APP_SKILLS")
        for category in categories:
            items.extend(
                row for row in db.list_catalog_items(category, scope="builtin", include_disabled=True)
                if not row.get("enabled", True)
                and not any(current["id"] == row["id"] for current in items)
            )
        items.sort(key=lambda row: (row["category"], row["sort"]))
    return items


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))[:4]
    return tuple(int(part) for part in parts) if parts else (0,)


def _catalog_revision(items: list[dict[str, Any]]) -> str:
    raw = json.dumps(
        {"items": items, "tools": db.list_tool_catalog(include_disabled=True)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _skill_compatibility(data: dict[str, Any], report: "CatalogPullBody") -> dict[str, Any]:
    tool_specs = {item["name"]: item for item in db.list_tool_catalog(include_disabled=True)}
    tools = [str(item) for item in data.get("tools", []) if str(item)]
    required_app = str(data.get("min_app_version") or "0.0.0")
    unsupported: list[str] = []
    platform_key = "macos" if report.platform.lower() == "darwin" else report.platform.lower()
    for name in tools:
        spec = tool_specs.get(name, {})
        minimum = str(spec.get("min_app_version") or "0.0.0")
        if _version_tuple(minimum) > _version_tuple(required_app):
            required_app = minimum
        required_contract = str(spec.get("contract_version") or "1")
        if spec.get("implementation_type") == "shell":
            scripts = spec.get("scripts") if isinstance(spec.get("scripts"), dict) else {}
            supported_contract = report.tool_contract_version if scripts.get(platform_key) else "0"
        else:
            supported_contract = str(report.supported_tools.get(name) or "0")
        if not spec.get("enabled", False) or _version_tuple(supported_contract) < _version_tuple(required_contract):
            unsupported.append(name)
    reasons: list[str] = []
    if _version_tuple(report.app_version) < _version_tuple(required_app):
        reasons.append(f"requires app {required_app}+")
    if unsupported:
        reasons.append("unsupported tools: " + ", ".join(sorted(unsupported)))
    return {
        "compatible": not reasons,
        "compatibility_error": "; ".join(reasons),
        "min_app_version": required_app,
        "unsupported_tools": sorted(unsupported),
    }


def _skill_bucket(account_id: str, slug: str) -> int:
    """稳定账号分桶；同一账号/slug 在灰度期间不会版本抖动。"""
    digest = hashlib.sha256(f"{account_id}:{slug}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100


def _project_skill_releases(items: list[dict[str, Any]], account: Account) -> list[dict[str, Any]]:
    """把 catalog 的公开投影解析成该账号确定可见的不可变 release。"""
    result: list[dict[str, Any]] = []
    account_id = str(getattr(account, "id", "anonymous") or "anonymous")
    now = time.time()
    for original in items:
        row = dict(original)
        if row.get("category") != "APP_SKILLS" or not isinstance(row.get("data"), dict):
            result.append(row)
            continue
        slug = str(row["data"].get("slug") or "")
        releases = db.list_skill_releases(slug=slug) if slug else []
        if not releases or not row.get("enabled", True):
            result.append(row)
            continue
        active = next((
            release for release in releases
            if release["state"] in {"rolling_out", "published"}
            and float(release.get("effective_at") or 0) <= now
        ), None)
        selected = active
        if active and active["state"] == "rolling_out":
            percent = int(active.get("rollout_percent") or 0)
            if _skill_bucket(account_id, slug) >= percent:
                selected = next((
                    release for release in releases
                    if release["state"] == "superseded" and release["version"] < active["version"]
                ), None)
        if active is None:
            selected = next((release for release in releases if release["state"] == "superseded"), None)
        if selected is None:
            # 新技能尚未到生效时间或账号未进入灰度，不下发半成品。
            continue
        data = _normalize_app_skill(selected["data"])
        data.update({
            "release_id": selected["id"], "release_version": selected["version"],
            "content_hash": selected["content_hash"],
        })
        row.update({"data": data, "version": selected["version"], "release_id": selected["id"]})
        result.append(row)
    return result


@router.get("/catalog")
def list_all_catalog(all: bool = False, account: Account = CurrentAccount) -> dict:
    """所有 builtin 目录项（跨 category），供客户端一次性下行覆盖本地。
    `?all=true`（仅平台管理员）连停用项一并返回，供门户高级 JSON 视图。"""
    inc = all and account.is_platform_admin
    items = _downlink_catalog_items(include_all=inc)
    if not inc:
        items = _project_skill_releases(items, account)
    return {"items": items, "revision": _catalog_revision(items)}


@router.get("/catalog/skill-tools")
def list_skill_tools(account: Account = CurrentAccount) -> dict:
    """兼容端点：只返回数据库中已启用且允许普通 Skill 绑定的工具。"""
    return {"tools": db.list_tool_catalog(bindable_only=True)}


@router.get("/catalog/tools")
def list_tools(all: bool = False, account: Account = CurrentAccount) -> dict:
    """内置工具管理目录；停用项仅平台管理员可见。实现代码和凭据不在目录中。"""
    include_disabled = bool(all and account.is_platform_admin)
    return {"tools": db.list_tool_catalog(include_disabled=include_disabled)}


class UpdateToolBody(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=80)
    risk_level: str | None = Field(default=None, pattern=r"^(low|medium|high|critical)$")
    enabled: bool | None = None
    bindable: bool | None = None
    min_app_version: str | None = Field(
        default=None, pattern=r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$",
    )
    sort: int | None = Field(default=None, ge=0)
    parameters: dict[str, Any] | None = None
    scripts: dict[str, str] | None = None
    permissions: list[str] | None = Field(default=None, max_length=30)
    contract_version: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+){0,3}$")
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    output_limit: int | None = Field(default=None, ge=1024, le=262144)


class CreateShellToolBody(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="脚本", max_length=80)
    risk_level: str = Field(default="high", pattern=r"^(medium|high|critical)$")
    enabled: bool = True
    bindable: bool = True
    min_app_version: str = Field(
        default="1.0.0", pattern=r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$",
    )
    contract_version: str = Field(default="1", pattern=r"^\d+(?:\.\d+){0,3}$")
    parameters: dict[str, Any] = Field(default_factory=lambda: {
        "type": "object", "properties": {},
    })
    scripts: dict[str, str] = Field(default_factory=dict)
    permissions: list[str] = Field(
        default_factory=lambda: ["workspace.read", "workspace.write", "process.execute"],
        max_length=30,
    )
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    output_limit: int = Field(default=65536, ge=1024, le=262144)
    sort: int = Field(default=0, ge=0)


def _validated_tool_schema(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "object":
        raise HTTPException(400, "tool parameters must be a JSON Schema object")
    if not isinstance(value.get("properties", {}), dict):
        raise HTTPException(400, "tool parameters.properties must be an object")
    required = value.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise HTTPException(400, "tool parameters.required must be a string array")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > _MAX_TOOL_SCHEMA_BYTES:
        raise HTTPException(400, "tool parameters schema is too large")
    return value


def _validated_tool_scripts(value: Any, *, enabled: bool) -> dict[str, str]:
    if not isinstance(value, dict):
        raise HTTPException(400, "tool scripts must be an object")
    unknown = set(value) - _SHELL_PLATFORMS
    if unknown:
        raise HTTPException(400, f"unknown tool script platform: {sorted(unknown)[0]}")
    scripts: dict[str, str] = {}
    for platform_name, content in value.items():
        if not isinstance(content, str):
            raise HTTPException(400, f"{platform_name} tool script must be text")
        normalized = content.strip()
        if not normalized:
            continue
        if len(normalized.encode("utf-8")) > _MAX_TOOL_SCRIPT_BYTES:
            raise HTTPException(400, f"{platform_name} tool script is too large")
        scripts[platform_name] = normalized
    if enabled and not scripts:
        raise HTTPException(400, "enabled shell tool requires at least one platform script")
    return scripts


def _validated_tool_permissions(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(400, "tool permissions must be an array")
    permissions = list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
    if not permissions or not all(_TOOL_PERMISSION_RE.fullmatch(item) for item in permissions):
        raise HTTPException(400, "invalid tool permission")
    if "process.execute" not in permissions:
        permissions.append("process.execute")
    return permissions


def _validated_shell_tool(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    if not _TOOL_NAME_RE.fullmatch(name):
        raise HTTPException(400, "invalid shell tool name")
    return {
        **data,
        "name": name,
        "parameters": _validated_tool_schema(data.get("parameters")),
        "scripts": _validated_tool_scripts(data.get("scripts"), enabled=bool(data.get("enabled", True))),
        "permissions": _validated_tool_permissions(data.get("permissions")),
    }


@router.post("/catalog/tools")
def create_shell_tool(body: CreateShellToolBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    data = _validated_shell_tool(body.model_dump())
    if db.get_tool_catalog(data["name"]) is not None:
        raise HTTPException(409, "tool already exists")
    return {"tool": db.create_shell_tool(actor_id=account.id, data=data)}


@router.patch("/catalog/tools/{name}")
def update_tool(name: str, body: UpdateToolBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    current = db.get_tool_catalog(name)
    if current is None:
        raise HTTPException(404, "tool not found")
    patch = body.model_dump(exclude_none=True)
    if patch.get("bindable") is True and current.get("exposure") != "skill":
        raise HTTPException(409, "only skill exposure tools can be made bindable")
    implementation_fields = {
        "parameters", "scripts", "permissions", "contract_version", "timeout_seconds", "output_limit",
    }
    if current.get("implementation_type") != "shell" and implementation_fields.intersection(patch):
        raise HTTPException(409, "native implementation contract is signed by AgentMate")
    if current.get("implementation_type") == "shell":
        merged = _validated_shell_tool({**current, **patch})
        patch = {key: merged[key] for key in patch}
    updated = db.update_tool_catalog(name, actor_id=account.id, patch=patch)
    return {"tool": updated}


@router.delete("/catalog/tools/{name}")
def delete_tool(name: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    current = db.get_tool_catalog(name)
    if current is None:
        raise HTTPException(404, "tool not found")
    if current.get("implementation_type") != "shell":
        raise HTTPException(409, "native tools cannot be deleted")
    if not db.delete_shell_tool(name, actor_id=account.id):
        raise HTTPException(409, "tool cannot be deleted")
    return {"ok": True}


@router.get("/catalog/tools/{name}/audit")
def tool_audit(name: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if db.get_tool_catalog(name) is None:
        raise HTTPException(404, "tool not found")
    return {"audit": db.list_tool_catalog_audit(name)}


class SkillReleaseBody(BaseModel):
    data: dict[str, Any]
    sort: int = 0
    catalog_item_id: str = ""
    base_release_id: str = ""
    min_app_version: str = "0.0.0"


class SkillReleaseTestBody(BaseModel):
    passed: bool
    client_run_id: str = Field(min_length=1, max_length=200)
    app_version: str = Field(min_length=1, max_length=40)
    supported_tools: dict[str, str] = Field(default_factory=dict)
    trace_id: str = Field(default="", max_length=200)
    artifacts: list[str] = Field(default_factory=list, max_length=20)
    error: str = Field(default="", max_length=1000)


class SkillPublishBody(BaseModel):
    rollout_percent: int = Field(default=100, ge=1, le=100)
    rollout_channel: str = Field(default="stable", pattern=r"^[A-Za-z0-9._-]+$")
    effective_at: float = Field(default=0, ge=0)


class SkillMetricBody(BaseModel):
    event: str


def _skill_release_payload(release: dict[str, Any]) -> dict[str, Any]:
    payload = dict(release)
    payload["audit"] = db.skill_release_audit(release["id"])
    payload["metrics"] = db.skill_release_metrics(release["id"])
    base = db.get_skill_release(str(release.get("base_release_id") or ""))
    before = base.get("data", {}) if base else {}
    after = release.get("data", {})
    before_tools = set(before.get("tools", [])) if isinstance(before, dict) else set()
    after_tools = set(after.get("tools", [])) if isinstance(after, dict) else set()
    changed = sorted(
        key for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    ) if isinstance(before, dict) and isinstance(after, dict) else []
    payload["diff"] = {
        "changed_fields": changed,
        "tools_added": sorted(after_tools - before_tools),
        "tools_removed": sorted(before_tools - after_tools),
        "permissions_before": _normalize_app_skill(before).get("permissions", []) if before else [],
        "permissions_after": _normalize_app_skill(after).get("permissions", []) if after else [],
    }
    return payload


def _publish_skill_release(release: dict[str, Any], actor_id: str, body: SkillPublishBody) -> dict[str, Any]:
    data = _normalize_app_skill(release["data"])
    data["min_app_version"] = str(release.get("min_app_version") or "0.0.0")
    item_id = str(release.get("catalog_item_id") or "")
    item = db.get_catalog_item(item_id) if item_id else None
    if item is None:
        existing = next((
            row for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True)
            if isinstance(row.get("data"), dict) and row["data"].get("slug") == release["slug"]
        ), None)
        item_id = existing["id"] if existing else db.create_catalog_item(
            category="APP_SKILLS", data=data, scope="builtin", sort=int(release.get("sort") or 0),
        )
    db.update_catalog_item(item_id, data=data, sort=int(release.get("sort") or 0), enabled=True)
    db.attach_skill_release_catalog_item(release["id"], item_id)
    db.supersede_other_skill_releases(release["slug"], release["id"])
    effective_at = body.effective_at or time.time()
    state = "published" if body.rollout_percent == 100 and effective_at <= time.time() else "rolling_out"
    updated = db.set_skill_release_state(
        release["id"], state, actor_id, rollout_channel=body.rollout_channel,
        rollout_percent=body.rollout_percent, effective_at=effective_at,
        action="published" if state == "published" else "rollout_started",
        details={"channel": body.rollout_channel, "percent": body.rollout_percent, "effective_at": effective_at},
    )
    return updated or release


@router.get("/catalog/skill-releases")
def list_releases(slug: str = "", catalog_item_id: str = "", account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    return {"releases": [_skill_release_payload(item) for item in db.list_skill_releases(
        slug=slug, catalog_item_id=catalog_item_id,
    )]}


@router.post("/catalog/skill-releases")
def create_release(body: SkillReleaseBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    data = _normalize_app_skill(body.data)
    data["min_app_version"] = body.min_app_version or str(data.get("min_app_version") or "0.0.0")
    _validate_app_skill(data, ignore_id=body.catalog_item_id)
    if body.catalog_item_id:
        item = db.get_catalog_item(body.catalog_item_id)
        if not item or item.get("category") != "APP_SKILLS":
            raise HTTPException(404, "skill catalog item not found")
        old_slug = str(item.get("data", {}).get("slug") or "")
        if old_slug and old_slug != data["slug"]:
            raise HTTPException(409, "skill slug is immutable after creation")
    base_release_id = body.base_release_id
    if not base_release_id and body.catalog_item_id:
        prior = db.list_skill_releases(catalog_item_id=body.catalog_item_id)
        base_release_id = prior[0]["id"] if prior else ""
    if base_release_id and not db.get_skill_release(base_release_id):
        raise HTTPException(404, "base skill release not found")
    release = db.create_skill_release(
        data=data, sort=body.sort, author_id=account.id, catalog_item_id=body.catalog_item_id,
        base_release_id=base_release_id, min_app_version=body.min_app_version,
    )
    return {"release": _skill_release_payload(release)}


@router.post("/catalog/skill-releases/{release_id}/test-result")
def record_release_test(
    release_id: str, body: SkillReleaseTestBody, account: Account = CurrentAccount,
) -> dict:
    release = db.get_skill_release(release_id)
    if not release:
        raise HTTPException(404, "skill release not found")
    if release["state"] not in {"draft", "testing"}:
        raise HTTPException(409, "only draft or testing release accepts test results")
    report = CatalogPullBody(app_version=body.app_version, supported_tools=body.supported_tools)
    compatibility = _skill_compatibility(release["data"], report)
    passed = bool(body.passed and compatibility["compatible"])
    test_report = {
        "passed": passed, "client_run_id": body.client_run_id, "runner_id": account.id,
        "app_version": body.app_version, "trace_id": body.trace_id,
        "artifacts": body.artifacts, "error": body.error if not passed else "", **compatibility,
    }
    updated = db.set_skill_release_state(
        release_id, "testing", account.id, test_status="passed" if passed else "failed",
        test_report=test_report, action="client_test_passed" if passed else "client_test_failed",
    )
    return {"release": _skill_release_payload(updated or release)}


@router.post("/catalog/skill-releases/{release_id}/approve")
def approve_release(release_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    release = db.get_skill_release(release_id)
    if not release:
        raise HTTPException(404, "skill release not found")
    if release["state"] != "testing" or release["test_status"] != "passed":
        raise HTTPException(409, "a passing client test is required before approval")
    if release["author_id"] == account.id:
        raise HTTPException(409, "release author cannot approve their own release")
    updated = db.set_skill_release_state(
        release_id, "approved", account.id, reviewer_id=account.id, action="approved",
    )
    return {"release": _skill_release_payload(updated or release)}


@router.post("/catalog/skill-releases/{release_id}/publish")
def publish_release(
    release_id: str, body: SkillPublishBody, account: Account = CurrentAccount,
) -> dict:
    _require_admin(account)
    release = db.get_skill_release(release_id)
    if not release:
        raise HTTPException(404, "skill release not found")
    if release["state"] != "approved" or not release["reviewer_id"]:
        raise HTTPException(409, "approved release required")
    return {"release": _skill_release_payload(_publish_skill_release(release, account.id, body))}


@router.post("/catalog/skill-releases/{release_id}/pause")
def pause_release(release_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    release = db.get_skill_release(release_id)
    if not release or release["state"] != "rolling_out":
        raise HTTPException(409, "only a rolling release can be paused")
    updated = db.set_skill_release_state(release_id, "approved", account.id, action="rollout_paused")
    return {"release": _skill_release_payload(updated or release)}


@router.post("/catalog/skill-releases/{release_id}/withdraw")
def withdraw_release(release_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    release = db.get_skill_release(release_id)
    if not release:
        raise HTTPException(404, "skill release not found")
    if release["state"] in {"withdrawn", "superseded"}:
        raise HTTPException(409, "skill release is not active")
    item_id = str(release.get("catalog_item_id") or "")
    if item_id:
        db.update_catalog_item(item_id, enabled=False)
    updated = db.set_skill_release_state(release_id, "withdrawn", account.id, action="withdrawn")
    return {"release": _skill_release_payload(updated or release)}


@router.post("/catalog/skill-releases/{release_id}/rollback")
def rollback_release(release_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    target = db.get_skill_release(release_id)
    if not target:
        raise HTTPException(404, "skill release not found")
    restored = db.create_skill_release(
        data=target["data"], sort=int(target.get("sort") or 0), author_id=account.id,
        catalog_item_id=str(target.get("catalog_item_id") or ""), base_release_id=target["id"],
        min_app_version=str(target.get("min_app_version") or "0.0.0"),
    )
    restored = db.set_skill_release_state(
        restored["id"], "approved", account.id, reviewer_id=account.id, test_status="passed",
        test_report={"passed": True, "rollback_from": target["id"]}, action="rollback_approved",
    ) or restored
    published = _publish_skill_release(restored, account.id, SkillPublishBody())
    db.record_skill_release_metric(published["id"], "rollback")
    return {"release": _skill_release_payload(published)}


@router.post("/catalog/skill-releases/{release_id}/metrics")
def record_release_metric(
    release_id: str, body: SkillMetricBody, account: Account = CurrentAccount,
) -> dict:
    if not db.get_skill_release(release_id):
        raise HTTPException(404, "skill release not found")
    try:
        metrics = db.record_skill_release_metric(release_id, body.event)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"metrics": metrics}


@router.get("/catalog/{category}")
def list_catalog(category: str, all: bool = False, account: Account = CurrentAccount) -> dict:
    """某 category 目录项。`?all=true`（仅平台管理员）含停用项 + `enabled` 标志，供门户 CRUD 列表。"""
    inc = all and account.is_platform_admin
    items = db.list_catalog_items(category, scope="builtin", include_disabled=inc)
    if category == "APP_SKILLS":
        if not inc:
            items = _project_skill_releases(items, account)
        items = [{**row, "data": _normalize_app_skill(row.get("data"))} for row in items]
    elif category == "SKILL_RECOMMENDATIONS":
        items = [{**row, "data": _normalize_skill_recommendation(row.get("data"))} for row in items]
    return {"category": category, "items": items}


class CatalogItemBody(BaseModel):
    category: str
    kind: str = ""
    data: Any = None  # 目录卡：数组(如 EXP_GRID 元组) 或对象(如 CONN_META)
    sort: int = 0


class CatalogPullBody(BaseModel):
    revision: str = ""
    app_version: str = "0.0.0"
    platform: str = ""
    arch: str = ""
    tool_contract_version: str = "0"
    supported_tools: dict[str, str] = Field(default_factory=dict)


@router.post("/catalog/pull")
def pull_catalog(body: CatalogPullBody, account: Account = CurrentAccount) -> dict:
    """Conditional capability-aware catalog snapshot for AgentMate App clients."""
    items = _project_skill_releases(_downlink_catalog_items(include_withdrawn=True), account)
    revision = _catalog_revision(items)
    if body.revision and body.revision == revision:
        return {"revision": revision, "unchanged": True, "items": [], "tools": []}
    rendered: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        if row.get("category") == "APP_SKILLS" and isinstance(row.get("data"), dict):
            row["data"] = _normalize_app_skill(row["data"])
            withdrawn = not bool(row.get("enabled", True))
            compatibility = _skill_compatibility(row["data"], body) if not withdrawn else {
                "compatible": False, "compatibility_error": "withdrawn",
                "min_app_version": str(row["data"].get("min_app_version") or "0.0.0"),
                "unsupported_tools": [],
            }
            row.update({"withdrawn": withdrawn, **compatibility})
        elif row.get("category") == "SKILL_RECOMMENDATIONS" and isinstance(row.get("data"), dict):
            row["data"] = _normalize_skill_recommendation(row["data"])
        rendered.append(row)
    return {
        "revision": revision,
        "unchanged": False,
        "items": rendered,
        "tools": db.list_tool_catalog(include_disabled=True),
    }


_MAX_SKILL_FILES = 128
_MAX_SKILL_FILES_BYTES = 1024 * 1024
_RESERVED_SKILL_FILES = {
    "skill.md", "_skillhub_meta.json", "_meta.json", "_agentmate_release.json", ".disabled",
}


def _skill_category_rows(*, include_disabled: bool = True) -> list[dict[str, Any]]:
    return db.list_catalog_items(
        "SKILL_CATEGORIES", scope="builtin", include_disabled=include_disabled,
    )


def _skill_category_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_slug: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for row in _skill_category_rows():
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        slug = str(data.get("slug") or "").strip()
        name = str(data.get("name") or "").strip()
        if slug:
            by_slug[slug] = row
        if name:
            by_name[name.casefold()] = row
    return by_slug, by_name


def _normalize_skill_category(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    by_slug, by_name = _skill_category_maps()
    category_slug = str(normalized.get("category_slug") or "").strip()
    category_name = str(normalized.get("category") or "").strip()
    row = by_slug.get(category_slug) if category_slug else by_name.get(category_name.casefold())
    if row is None and not category_slug and not category_name:
        row = by_slug.get("other")
    if row:
        category = row["data"]
        normalized["category_slug"] = str(category.get("slug") or "")
        normalized["category"] = str(category.get("name") or "")
    else:
        normalized["category_slug"] = category_slug
        normalized["category"] = category_name
    return normalized


def _normalize_app_skill(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = _normalize_skill_category(data)
    for key in ("slug", "name", "icon", "category", "description", "instructions"):
        normalized[key] = str(normalized.get(key, "")).strip()
    tools = normalized.get("tools", [])
    normalized["tools"] = list(dict.fromkeys(str(tool).strip() for tool in tools)) if isinstance(tools, list) else tools
    if isinstance(normalized["tools"], list):
        permissions = {
            item["name"]: tuple(item.get("permissions") or ())
            for item in db.list_tool_catalog(include_disabled=True)
        }
        normalized["permissions"] = sorted({
            permission
            for tool in normalized["tools"]
            for permission in permissions.get(tool, ())
        })
        normalized["tool_contract_version"] = "1"
    normalized["source"] = "Server"
    return normalized


def _validate_app_skill(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "APP_SKILLS data must be an object")
    slug = str(data.get("slug", "")).strip()
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    instructions = str(data.get("instructions", "")).strip()
    categorized = _normalize_skill_category(data)
    category_slug = str(categorized.get("category_slug") or "")
    category_row = next((row for row in _skill_category_rows() if row["data"].get("slug") == category_slug), None)
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid skill slug")
    if not name or not description or not instructions:
        raise HTTPException(400, "skill name, description and instructions are required")
    if len(name) > 120 or len(description) > 500 or len(instructions) > 50_000:
        raise HTTPException(400, "skill name, description or instructions is too long")
    if not category_row:
        raise HTTPException(400, "skill category must reference a managed category")
    if not category_row.get("enabled", False):
        current = db.get_catalog_item(ignore_id) if ignore_id else None
        current_data = _normalize_skill_category(current.get("data")) if current else {}
        current_slug = str(current_data.get("category_slug") or "") if isinstance(current_data, dict) else ""
        if current_slug != category_slug:
            raise HTTPException(409, "skill category is disabled")
    tools = data.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(tool, str) and tool.strip() for tool in tools):
        raise HTTPException(400, "skill tools must be a string list")
    tool_specs = {item["name"]: item for item in db.list_tool_catalog(include_disabled=True)}
    unknown_tools = sorted(set(tools) - set(tool_specs))
    if unknown_tools:
        raise HTTPException(400, f"unknown skill tools: {', '.join(unknown_tools)}")
    existing_internal: set[str] = set()
    if ignore_id:
        current = db.get_catalog_item(ignore_id)
        current_tools = current.get("data", {}).get("tools", []) if current and isinstance(current.get("data"), dict) else []
        existing_internal = {
            name for name in current_tools
            if tool_specs.get(name, {}).get("exposure") == "internal"
        }
    unavailable = sorted(
        name for name in set(tools)
        if not tool_specs[name].get("enabled", False)
        or (not tool_specs[name].get("bindable", False) and name not in existing_internal)
    )
    if unavailable:
        raise HTTPException(409, f"skill tools are disabled or not bindable: {', '.join(unavailable)}")
    files = data.get("files", [])
    if not isinstance(files, list):
        raise HTTPException(400, "skill files must be a list")
    if len(files) > _MAX_SKILL_FILES:
        raise HTTPException(413, f"skill files exceed {_MAX_SKILL_FILES} entries")
    seen: set[str] = set()
    total = 0
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("content"), str):
            raise HTTPException(400, "each skill file requires string path and content")
        raw_path = entry["path"].replace("\\", "/").strip()
        path = PurePosixPath(raw_path)
        if (
            not raw_path or len(raw_path) > 240 or path.is_absolute()
            or any(part in {"", ".", ".."} or ":" in part or "\x00" in part for part in path.parts)
        ):
            raise HTTPException(400, "invalid skill file path")
        canonical = path.as_posix().casefold()
        if path.name.casefold() in _RESERVED_SKILL_FILES:
            raise HTTPException(400, f"reserved skill file: {path.name}")
        if canonical in seen:
            raise HTTPException(409, "duplicate skill file path")
        seen.add(canonical)
        total += len(entry["content"].encode("utf-8"))
        if total > _MAX_SKILL_FILES_BYTES:
            raise HTTPException(413, "skill files exceed 1MB")
    for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True):
        if row["id"] != ignore_id and isinstance(row.get("data"), dict) and row["data"].get("slug") == slug:
            raise HTTPException(409, "skill slug already exists")


def _skill_recommendations() -> list[dict]:
    return db.list_catalog_items(
        "SKILL_RECOMMENDATIONS", scope="builtin", include_disabled=True,
    )


def _validate_skill_category(data: Any, *, ignore_id: str = "") -> dict[str, Any]:
    if not isinstance(data, dict):
        raise HTTPException(400, "SKILL_CATEGORIES data must be an object")
    normalized = {
        "slug": str(data.get("slug") or "").strip(),
        "name": str(data.get("name") or "").strip(),
        "icon": str(data.get("icon") or "🧩").strip() or "🧩",
        "description": str(data.get("description") or "").strip(),
    }
    if not _SKILL_SLUG_RE.fullmatch(normalized["slug"]):
        raise HTTPException(400, "invalid skill category slug")
    if not normalized["name"]:
        raise HTTPException(400, "skill category name is required")
    if len(normalized["name"]) > 80 or len(normalized["icon"]) > 16 or len(normalized["description"]) > 500:
        raise HTTPException(400, "skill category name, icon or description is too long")
    for row in _skill_category_rows():
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] == ignore_id:
            continue
        if current.get("slug") == normalized["slug"]:
            raise HTTPException(409, "skill category slug already exists")
        if str(current.get("name") or "").strip().casefold() == normalized["name"].casefold():
            raise HTTPException(409, "skill category name already exists")
    return normalized


def _skill_category_is_used(slug: str) -> bool:
    for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True):
        data = _normalize_skill_category(row.get("data"))
        if isinstance(data, dict) and data.get("category_slug") == slug:
            return True
    for release in db.list_skill_releases():
        data = _normalize_skill_category(release.get("data"))
        if isinstance(data, dict) and data.get("category_slug") == slug:
            return True
    for row in _skill_recommendations():
        raw = row.get("data") if isinstance(row.get("data"), dict) else {}
        if str(raw.get("provider") or "").lower() == "agentmate":
            continue  # AgentMate 推荐位继承 Skill，本体引用已在上方覆盖。
        data = _normalize_skill_category(raw)
        if isinstance(data, dict) and data.get("category_slug") == slug:
            return True
    return False


def _normalize_skill_recommendation(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    provider = str(normalized.get("provider") or "").strip().lower()
    normalized["provider"] = provider
    if provider == "agentmate":
        skill_slug = str(normalized.get("skill_slug") or "").strip()
        skill = next((
            _normalize_app_skill(row.get("data"))
            for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True)
            if isinstance(row.get("data"), dict) and row["data"].get("slug") == skill_slug
        ), None)
        if isinstance(skill, dict):
            normalized["category_slug"] = skill.get("category_slug", "")
            normalized["category"] = skill.get("category", "")
    else:
        normalized = _normalize_skill_category(normalized)
    return normalized


def _validate_skill_recommendation(data: Any, *, ignore_id: str = "") -> None:
    """推荐位只保存引用和运营元数据；安装包、Key 与文件内容仍留在 App 本机。"""
    if not isinstance(data, dict):
        raise HTTPException(400, "SKILL_RECOMMENDATIONS data must be an object")
    normalized = _normalize_skill_recommendation(data)
    provider = str(normalized.get("provider", "")).strip().lower()
    slug = str(normalized.get("skill_slug", "")).strip()
    placement = str(normalized.get("placement", "skills.recommended")).strip()
    if provider not in {"agentmate", "skillhub"}:
        raise HTTPException(400, "provider must be agentmate or skillhub")
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid recommendation skill slug")
    if not _PLACEMENT_RE.fullmatch(placement):
        raise HTTPException(400, "invalid recommendation placement")
    if provider == "agentmate":
        exists = any(
            isinstance(row.get("data"), dict) and row["data"].get("slug") == slug
            for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True)
        )
        if not exists:
            raise HTTPException(400, "referenced AgentMate skill does not exist")
    elif not str(normalized.get("title", "")).strip() or not str(normalized.get("description", "")).strip():
        raise HTTPException(400, "SkillHub recommendation title and description are required")
    category_slug = str(normalized.get("category_slug") or "")
    category_row = next((row for row in _skill_category_rows() if row["data"].get("slug") == category_slug), None)
    if not category_row:
        raise HTTPException(400, "recommendation category must reference a managed category")
    if not category_row.get("enabled", False):
        current = db.get_catalog_item(ignore_id) if ignore_id else None
        current_data = _normalize_skill_recommendation(current.get("data")) if current else {}
        if str(current_data.get("category_slug") or "") != category_slug:
            raise HTTPException(409, "recommendation category is disabled")
    try:
        starts_at = float(normalized.get("starts_at") or 0)
        ends_at = float(normalized.get("ends_at") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "invalid recommendation schedule") from exc
    if starts_at < 0 or ends_at < 0 or (starts_at and ends_at and ends_at <= starts_at):
        raise HTTPException(400, "recommendation end time must be later than start time")
    for row in _skill_recommendations():
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and (
            str(current.get("provider", "")).lower(), current.get("skill_slug"),
            current.get("placement", "skills.recommended"),
        ) == (provider, slug, placement):
            raise HTTPException(409, "skill recommendation already exists in this placement")


def _validate_skillhub_blocklist(data: Any, *, ignore_id: str = "") -> dict[str, str]:
    """Validate a policy row; Server distributes slugs only and never proxies SkillHub content."""
    if not isinstance(data, dict):
        raise HTTPException(400, "SKILLHUB_BLOCKLIST data must be an object")
    normalized = {
        "slug": str(data.get("slug") or "").strip(),
        "reason": str(data.get("reason") or "").strip(),
    }
    if not _SKILL_SLUG_RE.fullmatch(normalized["slug"]):
        raise HTTPException(400, "invalid SkillHub blocklist slug")
    if len(normalized["reason"]) > 500:
        raise HTTPException(400, "SkillHub blocklist reason is too long")
    for row in db.list_catalog_items("SKILLHUB_BLOCKLIST", scope="builtin", include_disabled=True):
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and str(current.get("slug") or "").casefold() == normalized["slug"].casefold():
            raise HTTPException(409, "SkillHub slug is already blocked")
    return normalized


def _skill_is_recommended(slug: str) -> bool:
    return any(
        isinstance(row.get("data"), dict)
        and str(row["data"].get("provider", "")).lower() == "agentmate"
        and row["data"].get("skill_slug") == slug
        for row in _skill_recommendations()
    )


def _connector_recommendations() -> list[dict]:
    return db.list_catalog_items(
        "CONNECTOR_RECOMMENDATIONS", scope="builtin", include_disabled=True,
    )


def _validate_connector_definition(data: Any, *, ignore_id: str = "") -> None:
    """只接受公开启动定义；secret_env 的键和值都只能是环境变量名，杜绝把密钥值写进 Server。"""
    if not isinstance(data, dict):
        raise HTTPException(400, "CONN_DEFS data must be an object")
    slug = str(data.get("slug", "")).strip()
    name = str(data.get("name", "")).strip()
    status = str(data.get("status", "")).strip()
    launch = data.get("launch")
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid connector slug")
    if not name:
        raise HTTPException(400, "connector name is required")
    if status not in {"rdy", "tok"}:
        raise HTTPException(400, "connector status must be rdy or tok")
    if not isinstance(launch, dict):
        raise HTTPException(400, "connector launch must be an object")
    builtin_server = str(launch.get("builtin_server", "")).strip()
    command = str(launch.get("command", "")).strip()
    if bool(builtin_server) == bool(command):
        raise HTTPException(400, "connector launch requires exactly one of builtin_server or command")
    if builtin_server and builtin_server not in _BUILTIN_CONNECTOR_SERVERS:
        raise HTTPException(400, "unknown builtin connector server")
    for key in ("requires", "requires_bin", "args"):
        value = launch.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise HTTPException(400, f"connector launch {key} must be a string list")
    for value in launch.get("requires", []):
        if not _ENV_NAME_RE.fullmatch(value):
            raise HTTPException(400, "invalid connector environment variable name")
    secret_env = launch.get("secret_env", {})
    if not isinstance(secret_env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and _ENV_NAME_RE.fullmatch(k) and _ENV_NAME_RE.fullmatch(v)
        for k, v in secret_env.items()
    ):
        raise HTTPException(400, "connector secret_env accepts environment variable names only")
    for row in db.list_catalog_items("CONN_DEFS", scope="builtin", include_disabled=True):
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and (current.get("slug") == slug or current.get("name") == name):
            raise HTTPException(409, "connector slug or name already exists")


def _validate_connector_recommendation(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "CONNECTOR_RECOMMENDATIONS data must be an object")
    slug = str(data.get("connector_slug", "")).strip()
    placement = str(data.get("placement", "connectors.recommended")).strip()
    if not _SKILL_SLUG_RE.fullmatch(slug) or not _PLACEMENT_RE.fullmatch(placement):
        raise HTTPException(400, "invalid connector recommendation")
    exists = any(
        isinstance(row.get("data"), dict) and row["data"].get("slug") == slug
        for row in db.list_catalog_items("CONN_DEFS", scope="builtin", include_disabled=True)
    )
    if not exists:
        raise HTTPException(400, "referenced connector does not exist")
    try:
        starts_at = float(data.get("starts_at") or 0)
        ends_at = float(data.get("ends_at") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "invalid recommendation schedule") from exc
    if starts_at < 0 or ends_at < 0 or (starts_at and ends_at and ends_at <= starts_at):
        raise HTTPException(400, "recommendation end time must be later than start time")
    for row in _connector_recommendations():
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and (
            current.get("connector_slug"), current.get("placement", "connectors.recommended")
        ) == (slug, placement):
            raise HTTPException(409, "connector recommendation already exists in this placement")


def _connector_is_recommended(slug: str) -> bool:
    return any(
        isinstance(row.get("data"), dict) and row["data"].get("connector_slug") == slug
        for row in _connector_recommendations()
    )


def _expert_recommendations() -> list[dict]:
    return db.list_catalog_items(
        "EXPERT_RECOMMENDATIONS", scope="builtin", include_disabled=True,
    )


def _validate_expert_definition(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "EXPERT_DEFS data must be an object")
    slug = str(data.get("slug", "")).strip()
    name = str(data.get("name", "")).strip()
    persona = str(data.get("persona", "")).strip()
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid expert slug")
    if not name or not persona:
        raise HTTPException(400, "expert name and persona are required")
    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise HTTPException(400, "expert tags must be a string list")
    if "functional" in data and not isinstance(data["functional"], bool):
        raise HTTPException(400, "expert functional must be boolean")
    for row in db.list_catalog_items("EXPERT_DEFS", scope="builtin", include_disabled=True):
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and (current.get("slug") == slug or current.get("name") == name):
            raise HTTPException(409, "expert slug or name already exists")


def _validate_expert_recommendation(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "EXPERT_RECOMMENDATIONS data must be an object")
    slug = str(data.get("expert_slug", "")).strip()
    placement = str(data.get("placement", "experts.recommended")).strip()
    if not _SKILL_SLUG_RE.fullmatch(slug) or not _PLACEMENT_RE.fullmatch(placement):
        raise HTTPException(400, "invalid expert recommendation")
    exists = any(
        isinstance(row.get("data"), dict) and row["data"].get("slug") == slug
        for row in db.list_catalog_items("EXPERT_DEFS", scope="builtin", include_disabled=True)
    )
    if not exists:
        raise HTTPException(400, "referenced expert does not exist")
    try:
        starts_at = float(data.get("starts_at") or 0)
        ends_at = float(data.get("ends_at") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "invalid recommendation schedule") from exc
    if starts_at < 0 or ends_at < 0 or (starts_at and ends_at and ends_at <= starts_at):
        raise HTTPException(400, "recommendation end time must be later than start time")
    for row in _expert_recommendations():
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and (
            current.get("expert_slug"), current.get("placement", "experts.recommended")
        ) == (slug, placement):
            raise HTTPException(409, "expert recommendation already exists in this placement")


def _validate_expert_team(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "EXP_TEAMS data must be an object")
    name = str(data.get("name", "")).strip()
    members = data.get("members", [])
    if not name or len(name) > 120:
        raise HTTPException(400, "expert team name is required")
    if not isinstance(members, list) or not members or len(members) > 20:
        raise HTTPException(400, "expert team requires 1-20 members")
    definitions = {
        str(row["data"].get("slug", ""))
        for row in db.list_catalog_items("EXPERT_DEFS", scope="builtin")
        if isinstance(row.get("data"), dict)
    }
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, dict):
            raise HTTPException(400, "expert team members must be objects")
        slug = str(member.get("expert_slug", "")).strip()
        role = str(member.get("role", "")).strip()
        display_name = str(member.get("name", "")).strip()
        if not _SKILL_SLUG_RE.fullmatch(slug) or not role or not display_name:
            raise HTTPException(400, "each expert team member requires role, name and expert_slug")
        if slug not in definitions:
            raise HTTPException(400, f"referenced expert does not exist or is disabled: {slug}")
        if slug in seen:
            raise HTTPException(409, f"duplicate expert in team: {slug}")
        seen.add(slug)
    for row in db.list_catalog_items("EXP_TEAMS", scope="builtin", include_disabled=True):
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and current.get("name") == name:
            raise HTTPException(409, "expert team name already exists")


def _expert_is_recommended(slug: str) -> bool:
    return any(
        isinstance(row.get("data"), dict) and row["data"].get("expert_slug") == slug
        for row in _expert_recommendations()
    )


def _expert_is_in_team(slug: str) -> bool:
    for row in db.list_catalog_items("EXP_TEAMS", scope="builtin", include_disabled=True):
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        members = data.get("members", [])
        if not isinstance(members, list):
            continue
        if any(
            isinstance(member, dict) and member.get("expert_slug") == slug
            for member in members
        ):
            return True
    return False


@router.post("/catalog")
def create_item(body: CatalogItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    data = body.data
    if body.category == "APP_SKILLS":
        raise HTTPException(409, "APP_SKILLS must be created through the skill release workflow")
    elif body.category == "SKILL_CATEGORIES":
        data = _validate_skill_category(body.data)
    elif body.category == "SKILL_RECOMMENDATIONS":
        data = _normalize_skill_recommendation(body.data)
        _validate_skill_recommendation(data)
    elif body.category == "SKILLHUB_BLOCKLIST":
        data = _validate_skillhub_blocklist(body.data)
    elif body.category == "CONN_DEFS":
        _validate_connector_definition(body.data)
    elif body.category == "CONNECTOR_RECOMMENDATIONS":
        _validate_connector_recommendation(body.data)
    elif body.category == "EXPERT_DEFS":
        _validate_expert_definition(body.data)
    elif body.category == "EXP_TEAMS":
        _validate_expert_team(body.data)
    elif body.category == "EXPERT_RECOMMENDATIONS":
        _validate_expert_recommendation(body.data)
    iid = db.create_catalog_item(
        category=body.category, data=data, scope="builtin", kind=body.kind, sort=body.sort,
    )
    return {"id": iid}


class UpdateItemBody(BaseModel):
    data: Any = None
    sort: int | None = None
    enabled: bool | None = None


@router.patch("/catalog/item/{item_id}")
def update_item(item_id: str, body: UpdateItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    item = db.get_catalog_item(item_id)
    if not item:
        raise HTTPException(404, "catalog item not found")
    data = body.data
    if item["category"] == "APP_SKILLS" and (body.data is not None or body.enabled is not None):
        raise HTTPException(409, "APP_SKILLS definition and state must use the skill release workflow")
    elif item["category"] == "SKILL_CATEGORIES" and body.data is not None:
        data = _validate_skill_category(body.data, ignore_id=item_id)
        old_slug = str(item.get("data", {}).get("slug", "")) if isinstance(item.get("data"), dict) else ""
        if old_slug and old_slug != data["slug"]:
            raise HTTPException(409, "skill category slug is immutable after creation")
    elif item["category"] == "SKILL_RECOMMENDATIONS" and body.data is not None:
        data = _normalize_skill_recommendation(body.data)
        _validate_skill_recommendation(data, ignore_id=item_id)
    elif item["category"] == "SKILLHUB_BLOCKLIST" and body.data is not None:
        data = _validate_skillhub_blocklist(body.data, ignore_id=item_id)
    elif item["category"] == "CONN_DEFS" and body.data is not None:
        _validate_connector_definition(body.data, ignore_id=item_id)
        old_slug = str(item.get("data", {}).get("slug", "")) if isinstance(item.get("data"), dict) else ""
        new_slug = str(body.data.get("slug", "")) if isinstance(body.data, dict) else ""
        if old_slug and old_slug != new_slug and _connector_is_recommended(old_slug):
            raise HTTPException(409, "connector is referenced by a recommendation")
    elif item["category"] == "CONNECTOR_RECOMMENDATIONS" and body.data is not None:
        _validate_connector_recommendation(body.data, ignore_id=item_id)
    elif item["category"] == "EXPERT_DEFS" and body.data is not None:
        _validate_expert_definition(body.data, ignore_id=item_id)
        old_slug = str(item.get("data", {}).get("slug", "")) if isinstance(item.get("data"), dict) else ""
        new_slug = str(body.data.get("slug", "")) if isinstance(body.data, dict) else ""
        if old_slug and old_slug != new_slug:
            raise HTTPException(409, "expert slug is immutable after creation")
    elif item["category"] == "EXP_TEAMS" and body.data is not None:
        _validate_expert_team(body.data, ignore_id=item_id)
    elif item["category"] == "EXPERT_RECOMMENDATIONS" and body.data is not None:
        _validate_expert_recommendation(body.data, ignore_id=item_id)
    if item["category"] == "EXPERT_DEFS" and body.enabled is False and isinstance(item.get("data"), dict):
        slug = str(item["data"].get("slug", ""))
        if slug and (_expert_is_recommended(slug) or _expert_is_in_team(slug)):
            raise HTTPException(409, "expert is referenced by a recommendation or team")
    if not db.update_catalog_item(item_id, data=data, sort=body.sort, enabled=body.enabled):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}


@router.delete("/catalog/item/{item_id}")
def delete_item(item_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    item = db.get_catalog_item(item_id)
    if not item:
        raise HTTPException(404, "catalog item not found")
    if item["category"] == "APP_SKILLS" and isinstance(item.get("data"), dict):
        slug = str(item["data"].get("slug", ""))
        if db.list_skill_releases(catalog_item_id=item_id):
            raise HTTPException(409, "published skill must be withdrawn through the release workflow")
        if slug and _skill_is_recommended(slug):
            raise HTTPException(409, "skill is referenced by a recommendation")
        # local-first 客户端可能仍持有该 slug 的项目引用和安装快照；保留身份记录，只归档。
        if not db.update_catalog_item(item_id, enabled=False):
            raise HTTPException(404, "catalog item not found")
        return {"ok": True, "archived": True}
    if item["category"] == "CONN_DEFS" and isinstance(item.get("data"), dict):
        slug = str(item["data"].get("slug", ""))
        if slug and _connector_is_recommended(slug):
            raise HTTPException(409, "connector is referenced by a recommendation")
    if item["category"] == "EXPERT_DEFS" and isinstance(item.get("data"), dict):
        slug = str(item["data"].get("slug", ""))
        if slug and (_expert_is_recommended(slug) or _expert_is_in_team(slug)):
            raise HTTPException(409, "expert is referenced by a recommendation or team")
    if item["category"] == "SKILL_CATEGORIES" and isinstance(item.get("data"), dict):
        slug = str(item["data"].get("slug", ""))
        if slug and _skill_category_is_used(slug):
            raise HTTPException(409, "skill category is still referenced")
    if not db.delete_catalog_item(item_id):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}
