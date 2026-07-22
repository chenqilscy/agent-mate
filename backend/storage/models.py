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
class Run:
    """One real execution inside a long-lived Session (WB-242)."""
    id: str
    session_id: str
    owner_id: str
    project_id: Optional[str]
    work_item_id: Optional[str]
    mode: str
    status: str
    workspace: str
    idempotency_key: Optional[str]
    retry_of: Optional[str]
    plan: list[dict[str, Any]]
    permission_snapshot: dict[str, Any]
    checkpoint: dict[str, Any]
    error_code: Optional[str]
    error_message: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    tool_calls: int
    started_at: Optional[float]
    ended_at: Optional[float]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Artifact:
    """A verifiable file produced by a Run (WB-242)."""
    id: str
    run_id: str
    owner_id: str
    project_id: Optional[str]
    kind: str
    path: str
    name: str
    mime_type: str
    source_tool: str
    size: int
    sha256: str
    validation_status: str
    validation: dict[str, Any]
    preview_path: Optional[str]
    acceptance_status: str
    accepted_by: Optional[str]
    accepted_at: Optional[float]
    created_at: float
    updated_at: float

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
    # local 项目：本机 owner 级 WeKnora id；server 项目：Console 下发的稳定项目 KB id。
    # 两者由 origin 区分，provider id 与凭据从不下发。
    knowledge_ids: list[str]
    created_at: float
    updated_at: float
    # 'local' = 本机创建；'server' = 从 Server 下行拉取的只读镜像（WB-062 Phase 2）。
    origin: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Expert:
    """自定义专家（我的专家 · WB-049）。owner 维度存储；召唤时其 persona 注入系统提示，
    命中优先于内置 EXPERTS 字典（见 agent/runtime.py）。"""
    id: str
    owner_id: str
    name: str
    subtitle: str  # 职称/一句话身份
    avatar: str  # emoji 头像
    intro: str  # 能力介绍（展示用）
    persona: str  # 人格指令（注入系统提示，真影响回答）
    tags: list[str]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CatalogExpert:
    """目录里的专家定义（WB-059）。scope='builtin' 为内置人格（persona 真注入、functional=True）；
    scope='org'/'user' 及 functional=False 的纯橱窗卡留给后续目录归并（WB-060）。"""
    id: str
    scope: str  # "builtin" | "org" | "user"
    owner_id: Optional[str]  # None for builtin; org_id / user_id 归属
    slug: str
    name: str
    subtitle: str
    avatar: str
    intro: str
    persona: str  # 注入系统提示的人格指令（真影响回答）
    tags: list[str]
    category: str
    badge: str
    source: str
    functional: bool  # persona 是否真注入生效（真定义 vs 纯橱窗卡）
    enabled: bool
    sort: int
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CatalogConnector:
    """目录里的连接器定义（WB-059）。launch = 启动 spec（builtin_server / command+args /
    secret_env / requires / requires_bin），运行时据此 spawn/接入 MCP。凭据仍只在 backend/.env。"""
    id: str
    scope: str  # "builtin" | "org" | "user"
    owner_id: Optional[str]
    slug: str  # Server 推荐位引用的稳定身份；loadout 迁移前仍保存 name
    name: str  # 连接器名，即 loadout/项目里引用的 key（如 "本地便签"）
    icon: str
    description: str
    status: str  # "rdy" 内置即用 | "tok" 需凭据/CLI | "catalog" 未接入橱窗卡
    launch: dict[str, Any]  # 启动 spec（存 JSON）
    enabled: bool
    sort: int
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
    # 专业 PM 字段（WB-108，与 Server 对齐、随 server-origin 项目双向同步）。
    priority: str = ""              # '' | low | medium | high | urgent
    start_date: Optional[str] = None  # "YYYY-MM-DD" or None（甘特起点）
    labels: list[str] = field(default_factory=list)
    parent_id: str = ""             # 自引用 → 子任务
    milestone_id: str = ""          # → milestones.id
    estimate_h: float = 0.0         # 工时预估/投入（WB-117，与 Server 对齐）
    spent_h: float = 0.0
    custom_fields: dict[str, Any] = field(default_factory=dict)
    dependency_ids: list[str] = field(default_factory=list)
    sprint_id: str = ""

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
    timeout_sec: int = 300
    max_attempts: int = 3
    retry_backoff_sec: int = 30
    max_total_tokens: int = 0  # 0 = unlimited
    notify_policy: str = "failure,recovery"
    concurrency_policy: str = "skip"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutomationFire:
    """One logical automation trigger, durable across restarts and retries."""

    id: str
    automation_id: str
    owner_id: str
    fire_key: str
    trigger_kind: str  # scheduled | manual | replay
    planned_at: float
    status: str  # queued | running | retry_wait | succeeded | dead_letter | ignored
    attempt: int
    max_attempts: int
    session_id: Optional[str]
    run_id: Optional[str]
    retry_of_run_id: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    next_attempt_at: Optional[float]
    notified: list[str]
    created_at: float
    updated_at: float
    finished_at: Optional[float]

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
