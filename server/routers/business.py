"""Server-first durable business API (WB-432).

Desktop UI, Console and migration tools share these routes. Server is the only
writer; the local backend is never updated from here.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

import business_store as store
import db
from auth import CurrentAccount
from models import Account, Role, can_manage, can_write


router = APIRouter(prefix="/api", tags=["business"])

_REQUEST_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_CREDENTIAL_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s]{1,480}$")
_SECRET_KEY_RE = re.compile(r"(^|[_-])(token|secret|password|api[_-]?key|authorization|credential)([_-]|$)", re.I)
_SESSION_KINDS = {"chat", "assistant", "projexec", "automation"}
_SESSION_STATUSES = {"idle", "running", "waiting", "done", "error"}
_RUN_MODES = {"exec", "plan", "ask"}
_RUN_STATUSES = {
    "queued", "leased", "running", "waiting_user", "recoverable",
    "completed", "succeeded", "failed", "cancelled",
}
_TRIGGER_KINDS = {"interval", "daily", "health_daily", "webhook"}


def _payload_hash(body: BaseModel) -> str:
    raw = json.dumps(body.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _request_key(value: str) -> str:
    key = value.strip()
    if key and not _REQUEST_KEY_RE.fullmatch(key):
        raise HTTPException(400, "invalid Idempotency-Key")
    return key


def _page(call) -> dict[str, Any]:
    try:
        items, next_cursor = call()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"items": items, "next_cursor": next_cursor}


def _project_role(
    project_id: str, account: Account, *, write: bool = False, manage: bool = False,
) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    if write and db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
    if manage and not can_manage(role):
        raise HTTPException(403, "project Admin role required")
    if write and not can_write(role):
        raise HTTPException(403, "Viewer is read-only")
    return role


def _record(
    table: str, record_id: str, account: Account, *, write: bool = False, manage: bool = False,
) -> dict[str, Any]:
    item = store.get_record(table, record_id)
    if item is None:
        raise HTTPException(404, "record not found")
    project_id = item.get("project_id")
    if project_id:
        _project_role(str(project_id), account, write=write, manage=manage)
    elif item["owner_id"] != account.id:
        raise HTTPException(404, "record not found")
    return item


def _mutation_error(exc: Exception) -> None:
    if isinstance(exc, store.IdempotencyConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, store.VersionConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(404, "record not found") from exc
    raise exc


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            raw_key = str(key)
            normalized = re.sub(r"[^a-z0-9]", "", raw_key.lower())
            if _SECRET_KEY_RE.search(raw_key) or any(
                marker in normalized
                for marker in ("token", "secret", "password", "apikey", "authorization", "credential")
            ):
                return True
            if _contains_secret_key(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _validate_channel_config(config: dict[str, Any], credential_ref: str) -> None:
    if _contains_secret_key(config):
        raise HTTPException(400, "channel public_config must not contain credentials or secrets")
    if credential_ref and not _CREDENTIAL_REF_RE.fullmatch(credential_ref):
        raise HTTPException(400, "credential_ref must be an opaque local/device URI")


def _validate_automation(values: dict[str, Any]) -> None:
    kind = values.get("trigger_kind")
    if kind not in _TRIGGER_KINDS:
        raise HTTPException(400, "unsupported trigger_kind")
    interval = int(values.get("interval_min", 60))
    if kind == "interval" and interval < 1:
        raise HTTPException(400, "interval_min must be >= 1")
    at_time = str(values.get("at_time", "09:00"))
    if kind in {"daily", "health_daily"}:
        try:
            hour, minute = (int(part) for part in at_time.split(":", 1))
            assert 0 <= hour < 24 and 0 <= minute < 60
        except (ValueError, AssertionError):
            raise HTTPException(400, "at_time must be HH:MM")
    for key, low, high in (
        ("timeout_sec", 1, 3600), ("max_attempts", 1, 10),
        ("retry_backoff_sec", 1, 86400), ("max_total_tokens", 0, 10_000_000),
    ):
        if not low <= int(values.get(key, low)) <= high:
            raise HTTPException(400, f"{key} must be between {low} and {high}")
    if values.get("concurrency_policy") != "skip":
        raise HTTPException(400, "concurrency_policy must be 'skip'")


class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    project_id: str | None = None
    space: str | None = Field(default=None, max_length=120)
    kind: str = "chat"


class SessionPatch(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: str | None = None
    space: str | None = Field(default=None, max_length=120)


@router.get("/sessions")
def list_sessions(
    project_id: str | None = None, limit: int = Query(50, ge=1, le=200), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    if project_id:
        _project_role(project_id, account)
    page = _page(lambda: store.list_scoped(
        "business_sessions", account_id=account.id, project_id=project_id, limit=limit, cursor=cursor,
    ))
    return {"sessions": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/sessions")
def create_session(
    body: SessionCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    if body.kind not in _SESSION_KINDS:
        raise HTTPException(400, "unsupported session kind")
    if body.project_id:
        _project_role(body.project_id, account, write=True)
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_sessions", entity_type="session", actor_id=account.id, owner_id=account.id,
            project_id=body.project_id,
            fields={"title": body.title.strip(), "space": body.space, "kind": body.kind, "status": "idle"},
            client_request_id=key, request_hash=_payload_hash(body) if key else "",
        )
    except Exception as exc:  # normalized below
        _mutation_error(exc)
        raise
    return {"session": item, "duplicate": duplicate}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, account: Account = CurrentAccount) -> dict:
    return _record("business_sessions", session_id, account)


@router.patch("/sessions/{session_id}")
def update_session(session_id: str, body: SessionPatch, account: Account = CurrentAccount) -> dict:
    item = _record("business_sessions", session_id, account, write=True)
    patch = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    if patch.get("status") not in _SESSION_STATUSES | {None}:
        raise HTTPException(400, "unsupported session status")
    if "title" in patch:
        patch["title"] = patch["title"].strip()
    try:
        return store.update_record(
            "business_sessions", session_id, entity_type="session", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"),
            expected_version=body.expected_version, fields=patch,
        )
    except Exception as exc:
        _mutation_error(exc)
        raise


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str, expected_version: int = Query(ge=1), account: Account = CurrentAccount,
) -> dict:
    item = _record("business_sessions", session_id, account, write=True)
    if item["owner_id"] != account.id and item.get("project_id"):
        _project_role(item["project_id"], account, write=True, manage=True)
    try:
        store.soft_delete(
            "business_sessions", session_id, entity_type="session", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"), expected_version=expected_version,
        )
    except Exception as exc:
        _mutation_error(exc)
    return {"ok": True}


class MessageCreate(BaseModel):
    role: str
    content: str = Field(max_length=1_000_000)
    actor_id: str | None = Field(default=None, max_length=120)
    run_id: str | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
    usage: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=20000)


@router.get("/sessions/{session_id}/messages")
def list_messages(
    session_id: str, limit: int = Query(100, ge=1, le=500), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    _record("business_sessions", session_id, account)
    page = _page(lambda: store.list_scoped(
        "business_messages", account_id=account.id, project_id=None, limit=limit, cursor=cursor,
        parent=("session_id", session_id), order_column="sequence", ascending=True,
    ))
    return {"messages": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/sessions/{session_id}/messages")
def create_message(
    session_id: str, body: MessageCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    session = _record("business_sessions", session_id, account, write=True)
    if body.role not in {"user", "assistant", "tool", "system"}:
        raise HTTPException(400, "unsupported message role")
    actor_id = body.actor_id or (account.id if body.role == "user" else body.role)
    if body.role == "user" and actor_id != account.id:
        raise HTTPException(403, "user messages cannot impersonate another actor")
    if body.role != "user" and actor_id not in {"assistant", "tool", "system"}:
        raise HTTPException(400, "non-user actor must be assistant, tool or system")
    if body.run_id:
        run = _record("business_runs", body.run_id, account)
        if run["session_id"] != session_id:
            raise HTTPException(400, "run does not belong to session")
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_messages", entity_type="message", actor_id=account.id, owner_id=account.id,
            project_id=session.get("project_id"),
            fields={
                "session_id": session_id, "run_id": body.run_id, "role": body.role,
                "content": body.content, "actor_id": actor_id,
                "trace": body.trace, "usage": body.usage, "error": body.error,
            }, client_request_id=key, request_hash=_payload_hash(body) if key else "",
            sequence_parent=("session_id", session_id),
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"message": item, "duplicate": duplicate}


class RunCreate(BaseModel):
    session_id: str
    work_item_id: str | None = None
    mode: str = "exec"
    workspace: str = Field(default="default", max_length=500)
    retry_of: str | None = None
    model_ref: str | None = Field(default=None, max_length=200)
    model_id: str | None = Field(default=None, max_length=200)
    model_snapshot: dict[str, Any] = Field(default_factory=dict)
    permission_snapshot: dict[str, Any] = Field(default_factory=dict)
    target_device_id: str = Field(default="", max_length=200)
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    max_recoveries: int = Field(default=3, ge=0, le=20)


class RunPatch(BaseModel):
    expected_version: int = Field(ge=1)
    status: str | None = None
    plan: list[dict[str, Any]] | None = None
    plan_version: int | None = Field(default=None, ge=0)
    checkpoint: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=200)
    error_message: str | None = Field(default=None, max_length=20000)
    prompt_tokens: int | None = Field(default=None, ge=0)
    cached_prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, max_length=12)
    started_at: float | None = None
    ended_at: float | None = None


@router.get("/runs")
def list_runs(
    project_id: str | None = None, session_id: str | None = None,
    limit: int = Query(50, ge=1, le=200), cursor: str = "", account: Account = CurrentAccount,
) -> dict:
    parent = None
    if session_id:
        _record("business_sessions", session_id, account)
        parent = ("session_id", session_id)
    elif project_id:
        _project_role(project_id, account)
    page = _page(lambda: store.list_scoped(
        "business_runs", account_id=account.id, project_id=project_id, limit=limit,
        cursor=cursor, parent=parent,
    ))
    return {"runs": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/runs")
def create_run(
    body: RunCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    session = _record("business_sessions", body.session_id, account, write=True)
    if body.mode not in _RUN_MODES:
        raise HTTPException(400, "unsupported run mode")
    if body.retry_of:
        retry = _record("business_runs", body.retry_of, account)
        if retry["session_id"] != body.session_id:
            raise HTTPException(400, "retry_of does not belong to session")
    if len(set(body.required_capabilities)) != len(body.required_capabilities) or any(
        not item or len(item) > 200 for item in body.required_capabilities
    ):
        raise HTTPException(400, "required_capabilities must contain unique non-empty values")
    if _contains_secret_key(body.request_snapshot):
        raise HTTPException(400, "request_snapshot must not contain credentials or secrets")
    if len(json.dumps(body.request_snapshot, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
        raise HTTPException(413, "request_snapshot exceeds size limit")
    if body.target_device_id:
        target = db.get_conn().execute(
            "SELECT owner_id,status FROM agent_devices WHERE id=?", (body.target_device_id,),
        ).fetchone()
        if target is None or str(target["owner_id"]) != account.id or str(target["status"]) != "active":
            raise HTTPException(400, "target device is not an active device owned by this account")
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_runs", entity_type="run", actor_id=account.id, owner_id=account.id,
            project_id=session.get("project_id"), fields={
                "session_id": body.session_id, "work_item_id": body.work_item_id,
                "mode": body.mode, "status": "queued", "workspace": body.workspace,
                "retry_of": body.retry_of, "model_ref": body.model_ref, "model_id": body.model_id,
                "model_snapshot": body.model_snapshot, "permission_snapshot": body.permission_snapshot,
                "target_device_id": body.target_device_id,
                "required_capabilities": body.required_capabilities,
                "request_snapshot": body.request_snapshot,
                "max_recoveries": body.max_recoveries,
            }, client_request_id=key, request_hash=_payload_hash(body) if key else "",
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"run": item, "duplicate": duplicate}


@router.get("/runs/{run_id}")
def get_run(run_id: str, account: Account = CurrentAccount) -> dict:
    return _record("business_runs", run_id, account)


@router.patch("/runs/{run_id}")
def update_run(run_id: str, body: RunPatch, account: Account = CurrentAccount) -> dict:
    item = _record("business_runs", run_id, account, write=True)
    patch = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    if patch.get("status") not in _RUN_STATUSES | {None}:
        raise HTTPException(400, "unsupported run status")
    try:
        return store.update_record(
            "business_runs", run_id, entity_type="run", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"),
            expected_version=body.expected_version, fields=patch,
        )
    except Exception as exc:
        _mutation_error(exc)
        raise


class RunStepCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=120)
    status: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    started_at: float | None = None
    ended_at: float | None = None


@router.get("/runs/{run_id}/steps")
def list_run_steps(
    run_id: str, limit: int = Query(100, ge=1, le=500), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    _record("business_runs", run_id, account)
    page = _page(lambda: store.list_scoped(
        "business_run_steps", account_id=account.id, project_id=None, limit=limit, cursor=cursor,
        parent=("run_id", run_id), order_column="sequence", ascending=True,
    ))
    return {"steps": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/runs/{run_id}/steps")
def create_run_step(
    run_id: str, body: RunStepCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    run = _record("business_runs", run_id, account, write=True)
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_run_steps", entity_type="run_step", actor_id=account.id, owner_id=account.id,
            project_id=run.get("project_id"), fields={
                "run_id": run_id, "kind": body.kind, "status": body.status,
                "payload": body.payload, "started_at": body.started_at, "ended_at": body.ended_at,
            }, client_request_id=key, request_hash=_payload_hash(body) if key else "",
            sequence_parent=("run_id", run_id),
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"step": item, "duplicate": duplicate}


class AssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    project_id: str | None = None
    avatar: str = Field(default="", max_length=16)
    instruction: str = Field(default="", max_length=8000)
    model_ref: str | None = Field(default=None, max_length=200)
    mode: str = "exec"
    workspace: str = Field(default="default", max_length=500)
    experts: list[str] = Field(default_factory=list, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=100)
    connectors: list[str] = Field(default_factory=list, max_length=100)
    enabled: bool = True


class AssistantPatch(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    avatar: str | None = Field(default=None, max_length=16)
    instruction: str | None = Field(default=None, max_length=8000)
    model_ref: str | None = Field(default=None, max_length=200)
    mode: str | None = None
    workspace: str | None = Field(default=None, max_length=500)
    experts: list[str] | None = Field(default=None, max_length=100)
    skills: list[str] | None = Field(default=None, max_length=100)
    connectors: list[str] | None = Field(default=None, max_length=100)
    enabled: bool | None = None


@router.get("/assistants")
def list_assistants(
    project_id: str | None = None, limit: int = Query(50, ge=1, le=200), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    if project_id:
        _project_role(project_id, account)
    page = _page(lambda: store.list_scoped(
        "business_assistants", account_id=account.id, project_id=project_id, limit=limit, cursor=cursor,
    ))
    return {"assistants": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/assistants")
def create_assistant(
    body: AssistantCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    if body.mode not in _RUN_MODES:
        raise HTTPException(400, "unsupported assistant mode")
    if body.project_id:
        _project_role(body.project_id, account, write=True, manage=True)
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_assistants", entity_type="assistant", actor_id=account.id, owner_id=account.id,
            project_id=body.project_id, fields={
                "name": body.name.strip(), "avatar": body.avatar, "instruction": body.instruction,
                "model_ref": body.model_ref, "mode": body.mode, "workspace": body.workspace,
                "experts": body.experts, "skills": db.canonical_skill_keys(body.skills),
                "connectors": body.connectors, "enabled": body.enabled,
            }, client_request_id=key, request_hash=_payload_hash(body) if key else "",
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"assistant": item, "duplicate": duplicate}


@router.get("/assistants/{assistant_id}")
def get_assistant(assistant_id: str, account: Account = CurrentAccount) -> dict:
    assistant = _record("business_assistants", assistant_id, account)
    channels, _cursor = store.list_scoped(
        "business_channels", account_id=account.id, project_id=None, limit=200,
        parent=("assistant_id", assistant_id),
    )
    return {**assistant, "channels": channels}


@router.patch("/assistants/{assistant_id}")
def update_assistant(assistant_id: str, body: AssistantPatch, account: Account = CurrentAccount) -> dict:
    item = _record("business_assistants", assistant_id, account, write=True, manage=bool(
        store.get_record("business_assistants", assistant_id).get("project_id")
    ))
    patch = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    if patch.get("mode") not in _RUN_MODES | {None}:
        raise HTTPException(400, "unsupported assistant mode")
    if "skills" in patch:
        patch["skills"] = db.canonical_skill_keys(patch["skills"])
    if "name" in patch:
        patch["name"] = patch["name"].strip()
    try:
        return store.update_record(
            "business_assistants", assistant_id, entity_type="assistant", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"),
            expected_version=body.expected_version, fields=patch,
        )
    except Exception as exc:
        _mutation_error(exc)
        raise


@router.delete("/assistants/{assistant_id}")
def delete_assistant(
    assistant_id: str, expected_version: int = Query(ge=1), account: Account = CurrentAccount,
) -> dict:
    item = _record("business_assistants", assistant_id, account, write=True)
    if item.get("project_id"):
        _project_role(item["project_id"], account, write=True, manage=True)
    try:
        store.soft_delete(
            "business_assistants", assistant_id, entity_type="assistant", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"), expected_version=expected_version,
        )
    except Exception as exc:
        _mutation_error(exc)
    return {"ok": True}


class ChannelCreate(BaseModel):
    type: str = Field(min_length=1, max_length=80)
    public_config: dict[str, Any] = Field(default_factory=dict)
    credential_ref: str = Field(default="", max_length=500)
    enabled: bool = False


class ChannelPatch(BaseModel):
    expected_version: int = Field(ge=1)
    public_config: dict[str, Any] | None = None
    credential_ref: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


def _channel(channel_id: str, assistant: dict[str, Any], account: Account) -> dict[str, Any]:
    item = store.get_record("business_channels", channel_id)
    if item is None or item["assistant_id"] != assistant["id"]:
        raise HTTPException(404, "channel not found")
    if assistant.get("project_id"):
        _project_role(assistant["project_id"], account)
    elif assistant["owner_id"] != account.id:
        raise HTTPException(404, "channel not found")
    return item


@router.get("/assistants/{assistant_id}/channels")
def list_channels(
    assistant_id: str, limit: int = Query(50, ge=1, le=200), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    _record("business_assistants", assistant_id, account)
    page = _page(lambda: store.list_scoped(
        "business_channels", account_id=account.id, project_id=None, limit=limit, cursor=cursor,
        parent=("assistant_id", assistant_id),
    ))
    return {"channels": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/assistants/{assistant_id}/channels")
def create_channel(
    assistant_id: str, body: ChannelCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    assistant = _record("business_assistants", assistant_id, account, write=True)
    if assistant.get("project_id"):
        _project_role(assistant["project_id"], account, write=True, manage=True)
    _validate_channel_config(body.public_config, body.credential_ref)
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_channels", entity_type="channel", actor_id=account.id, owner_id=account.id,
            project_id=assistant.get("project_id"), fields={
                "assistant_id": assistant_id, "type": body.type, "public_config": body.public_config,
                "credential_ref": body.credential_ref, "enabled": body.enabled,
            }, client_request_id=key, request_hash=_payload_hash(body) if key else "",
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"channel": item, "duplicate": duplicate}


@router.patch("/assistants/{assistant_id}/channels/{channel_id}")
def update_channel(
    assistant_id: str, channel_id: str, body: ChannelPatch, account: Account = CurrentAccount,
) -> dict:
    assistant = _record("business_assistants", assistant_id, account, write=True)
    item = _channel(channel_id, assistant, account)
    if assistant.get("project_id"):
        _project_role(assistant["project_id"], account, write=True, manage=True)
    patch = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    _validate_channel_config(
        patch.get("public_config", item["public_config"]),
        patch.get("credential_ref", item["credential_ref"]),
    )
    try:
        return store.update_record(
            "business_channels", channel_id, entity_type="channel", actor_id=account.id,
            owner_id=item["owner_id"], project_id=assistant.get("project_id"),
            expected_version=body.expected_version, fields=patch,
        )
    except Exception as exc:
        _mutation_error(exc)
        raise


@router.delete("/assistants/{assistant_id}/channels/{channel_id}")
def delete_channel(
    assistant_id: str, channel_id: str, expected_version: int = Query(ge=1),
    account: Account = CurrentAccount,
) -> dict:
    assistant = _record("business_assistants", assistant_id, account, write=True)
    item = _channel(channel_id, assistant, account)
    if assistant.get("project_id"):
        _project_role(assistant["project_id"], account, write=True, manage=True)
    try:
        store.soft_delete(
            "business_channels", channel_id, entity_type="channel", actor_id=account.id,
            owner_id=item["owner_id"], project_id=assistant.get("project_id"),
            expected_version=expected_version,
        )
    except Exception as exc:
        _mutation_error(exc)
    return {"ok": True}


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=200000)
    project_id: str | None = None
    trigger_kind: str = "interval"
    interval_min: int = 60
    at_time: str = Field(default="09:00", max_length=5)
    model_ref: str | None = Field(default=None, max_length=200)
    enabled: bool = True
    timeout_sec: int = 300
    max_attempts: int = 3
    retry_backoff_sec: int = 30
    max_total_tokens: int = 0
    notify_policy: str = "failure,recovery"
    concurrency_policy: str = "skip"
    preauthorized_permissions: list[str] = Field(default_factory=list, max_length=100)


class AutomationPatch(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(default=None, min_length=1, max_length=200000)
    trigger_kind: str | None = None
    interval_min: int | None = None
    at_time: str | None = Field(default=None, max_length=5)
    model_ref: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    next_run_at: float | None = None
    last_run_at: float | None = None
    last_session_id: str | None = None
    last_status: str | None = Field(default=None, max_length=80)
    timeout_sec: int | None = None
    max_attempts: int | None = None
    retry_backoff_sec: int | None = None
    max_total_tokens: int | None = None
    notify_policy: str | None = None
    concurrency_policy: str | None = None
    preauthorized_permissions: list[str] | None = Field(default=None, max_length=100)


@router.get("/automations")
def list_automations(
    project_id: str | None = None, limit: int = Query(50, ge=1, le=200), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    if project_id:
        _project_role(project_id, account)
    page = _page(lambda: store.list_scoped(
        "business_automations", account_id=account.id, project_id=project_id, limit=limit, cursor=cursor,
    ))
    return {"automations": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/automations")
def create_automation(
    body: AutomationCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    values = body.model_dump()
    _validate_automation(values)
    if body.trigger_kind == "health_daily" and not body.project_id:
        raise HTTPException(400, "health_daily requires project_id")
    if body.project_id:
        _project_role(body.project_id, account, write=True, manage=True)
    project_id = values.pop("project_id")
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_automations", entity_type="automation", actor_id=account.id, owner_id=account.id,
            project_id=project_id, fields=values, client_request_id=key,
            request_hash=_payload_hash(body) if key else "",
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"automation": item, "duplicate": duplicate}


@router.get("/automations/{automation_id}")
def get_automation(automation_id: str, account: Account = CurrentAccount) -> dict:
    return _record("business_automations", automation_id, account)


@router.patch("/automations/{automation_id}")
def update_automation(
    automation_id: str, body: AutomationPatch, account: Account = CurrentAccount,
) -> dict:
    item = _record("business_automations", automation_id, account, write=True)
    if item.get("project_id"):
        _project_role(item["project_id"], account, write=True, manage=True)
    patch = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    merged = {**item, **patch}
    _validate_automation(merged)
    if patch.get("last_session_id"):
        session = _record("business_sessions", patch["last_session_id"], account)
        if session.get("project_id") != item.get("project_id"):
            raise HTTPException(400, "last_session_id scope mismatch")
    try:
        return store.update_record(
            "business_automations", automation_id, entity_type="automation", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"),
            expected_version=body.expected_version, fields=patch,
        )
    except Exception as exc:
        _mutation_error(exc)
        raise


@router.delete("/automations/{automation_id}")
def delete_automation(
    automation_id: str, expected_version: int = Query(ge=1), account: Account = CurrentAccount,
) -> dict:
    item = _record("business_automations", automation_id, account, write=True)
    if item.get("project_id"):
        _project_role(item["project_id"], account, write=True, manage=True)
    try:
        store.soft_delete(
            "business_automations", automation_id, entity_type="automation", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"), expected_version=expected_version,
        )
    except Exception as exc:
        _mutation_error(exc)
    return {"ok": True}


class AssetCreate(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    kind: str = Field(default="asset", max_length=80)
    name: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(default="application/octet-stream", max_length=200)
    size: int = Field(default=0, ge=0)
    sha256: str = Field(default="", pattern=r"^$|^[0-9a-fA-F]{64}$")
    storage_state: str = "pending"
    object_ref: str = Field(default="", max_length=1000)
    source_tool: str = Field(default="", max_length=200)
    validation_status: str = Field(default="pending", max_length=80)
    validation: dict[str, Any] = Field(default_factory=dict)


class AssetPatch(BaseModel):
    expected_version: int = Field(ge=1)
    storage_state: str | None = Field(default=None, max_length=80)
    object_ref: str | None = Field(default=None, max_length=1000)
    validation_status: str | None = Field(default=None, max_length=80)
    validation: dict[str, Any] | None = None
    acceptance_status: str | None = Field(default=None, max_length=80)
    accepted_by: str | None = Field(default=None, max_length=120)
    accepted_at: float | None = None


@router.get("/assets")
def list_assets(
    project_id: str | None = None, run_id: str | None = None,
    limit: int = Query(50, ge=1, le=200), cursor: str = "", account: Account = CurrentAccount,
) -> dict:
    parent = None
    if run_id:
        _record("business_runs", run_id, account)
        parent = ("run_id", run_id)
    elif project_id:
        _project_role(project_id, account)
    page = _page(lambda: store.list_scoped(
        "business_assets", account_id=account.id, project_id=project_id, limit=limit,
        cursor=cursor, parent=parent,
    ))
    return {"assets": page["items"], "next_cursor": page["next_cursor"]}


@router.post("/assets")
def create_asset(
    body: AssetCreate, account: Account = CurrentAccount,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> dict:
    if body.storage_state != "pending" or body.object_ref:
        raise HTTPException(400, "asset object state is managed by the upload protocol")
    project_id = body.project_id
    session = None
    run = None
    if body.session_id:
        session = _record("business_sessions", body.session_id, account, write=True)
        project_id = project_id or session.get("project_id")
        if session.get("project_id") != project_id:
            raise HTTPException(400, "session scope mismatch")
    if body.run_id:
        run = _record("business_runs", body.run_id, account, write=True)
        project_id = project_id or run.get("project_id")
        if run.get("project_id") != project_id:
            raise HTTPException(400, "run scope mismatch")
        if session and run["session_id"] != session["id"]:
            raise HTTPException(400, "run does not belong to session")
    if project_id:
        _project_role(project_id, account, write=True)
    values = body.model_dump(exclude={"project_id"})
    key = _request_key(idempotency_key)
    try:
        item, duplicate = store.create_record(
            "business_assets", entity_type="asset", actor_id=account.id, owner_id=account.id,
            project_id=project_id, fields=values, client_request_id=key,
            request_hash=_payload_hash(body) if key else "",
        )
    except Exception as exc:
        _mutation_error(exc)
        raise
    return {"asset": item, "duplicate": duplicate}


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, account: Account = CurrentAccount) -> dict:
    return _record("business_assets", asset_id, account)


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: str, body: AssetPatch, account: Account = CurrentAccount) -> dict:
    item = _record("business_assets", asset_id, account, write=True)
    if body.storage_state is not None or body.object_ref is not None:
        raise HTTPException(400, "asset object state is managed by the upload protocol")
    patch = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    try:
        return store.update_record(
            "business_assets", asset_id, entity_type="asset", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"),
            expected_version=body.expected_version, fields=patch,
        )
    except Exception as exc:
        _mutation_error(exc)
        raise


@router.delete("/assets/{asset_id}")
def delete_asset(
    asset_id: str, expected_version: int = Query(ge=1), account: Account = CurrentAccount,
) -> dict:
    item = _record("business_assets", asset_id, account, write=True)
    try:
        store.soft_delete(
            "business_assets", asset_id, entity_type="asset", actor_id=account.id,
            owner_id=item["owner_id"], project_id=item.get("project_id"), expected_version=expected_version,
        )
    except Exception as exc:
        _mutation_error(exc)
    return {"ok": True}


@router.get("/business/audit")
def business_audit(
    project_id: str | None = None, limit: int = Query(100, ge=1, le=500), cursor: str = "",
    account: Account = CurrentAccount,
) -> dict:
    if project_id:
        _project_role(project_id, account)
    page = _page(lambda: store.list_audit(
        account_id=account.id, project_id=project_id, limit=limit, cursor=cursor,
    ))
    return {"audit": page["items"], "next_cursor": page["next_cursor"]}
