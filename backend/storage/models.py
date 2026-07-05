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
    kind: str  # "chat" | "assistant" | "projexec"
    status: str  # "idle" | "running" | "waiting" | "done"
    created_at: float
    updated_at: float

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
