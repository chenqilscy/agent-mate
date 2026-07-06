"""Domain models.

Multi-user is pre-embedded from M1 (decision A.3): every business row carries
UUID primary keys plus owner_id / project_id, and roles are a fixed enum. In
single-machine mode these are filled with the fixed local user, so switching on
the account system later (M7) touches only the auth middleware, not these tables.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


class Role(str, enum.Enum):
    OWNER = "Owner"
    ADMIN = "Admin"
    MEMBER = "Member"
    VIEWER = "Viewer"


# The fixed local user injected in single-machine mode.
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_USER_NAME = "奇"


@dataclass
class User:
    id: str
    name: str
    role: Role = Role.OWNER
    plan: str = "体验版"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        return d


@dataclass
class Session:
    id: str
    title: str
    owner_id: str
    project_id: Optional[str]
    space: Optional[str]
    kind: str  # "chat" | "assistant" | "projexec" | "automation"
    status: str  # "idle" | "running" | "waiting" | "done"
    created_at: float
    updated_at: float
    # Per-run outcome for automation runs (WB-043); None for ordinary chat/project
    # sessions. run_status: 'running' | 'ok' | 'error'; run_kind: 'test' | 'scheduled'.
    run_status: Optional[str] = None
    run_summary: Optional[str] = None
    run_kind: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Project:
    id: str
    name: str
    owner_id: str
    instruction: str
    connectors: list[str]
    experts: list[str]
    skills: list[str]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkItem:
    id: str
    project_id: str
    owner_id: str
    title: str
    status: str  # todo | doing | paused | done
    source: str  # "手动" | "执行" …
    assignee: str  # actor / user id
    created_at: float
    updated_at: float
    description: str = ""
    due_date: Optional[str] = None  # "YYYY-MM-DD" or None
    # 引用列表，元素形如 {"name": str, "kind": "local"|"asset", "path": str|None}。
    # 只存引用，不复制文件（项目资产引用项目云盘现有文件）。
    attachments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Automation:
    id: str
    owner_id: str
    name: str
    prompt: str
    trigger_kind: str  # "interval" | "daily"
    interval_min: int  # for trigger_kind == "interval"
    at_time: str  # "HH:MM" (local) for trigger_kind == "daily"
    project_id: Optional[str]
    model: Optional[str]
    enabled: bool
    created_at: float
    updated_at: float
    next_run_at: float
    last_run_at: Optional[float] = None
    last_session_id: Optional[str] = None
    last_status: Optional[str] = None  # "ok" | "error" | "running"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Message:
    id: str
    session_id: str
    role: str  # "user" | "assistant"
    content: str
    actor: str  # user id or "assistant" — for the future team timeline
    trace: list[dict[str, Any]] = field(default_factory=list)
    usage: Optional[dict[str, Any]] = None
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
