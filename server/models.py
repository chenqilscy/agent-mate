"""Server domain models（WB-061）。

Role 枚举与 backend/storage/models.py 逐字一致，让本地与 Server 的角色语义无缝对接
（Owner > Admin > Member > Viewer）。将来可抽到共享模块，避免两处漂移（见架构设计 §9）。
"""
from __future__ import annotations

import enum
from dataclasses import asdict, dataclass
from typing import Any, Optional


class Role(str, enum.Enum):
    OWNER = "Owner"
    ADMIN = "Admin"
    MEMBER = "Member"
    VIEWER = "Viewer"


# 权限比较用的等级：数值越大权限越高。Viewer 只读、Member 可写、Admin/Owner 可管成员。
ROLE_RANK: dict[Role, int] = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


def can_write(role: Optional[Role]) -> bool:
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[Role.MEMBER]


def can_manage(role: Optional[Role]) -> bool:
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[Role.ADMIN]


@dataclass
class Account:
    id: str
    name: str
    email: str
    plan: str
    created_at: float
    # 平台超级管理员：可维护 builtin 目录下发（WB-066）。首个注册账号自举为 admin。
    is_platform_admin: bool = False
    password_login_enabled: bool = True
    suspended_at: float = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Org:
    id: str
    name: str
    owner_id: str  # account id
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Project:
    id: str
    name: str
    org_id: Optional[str]  # None = 个人项目（无组织）
    owner_id: str  # account id
    instruction: str
    connectors: list[str]
    experts: list[str]
    skills: list[str]
    created_at: float
    updated_at: float
    archived_at: float = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Invite:
    id: str
    code: str
    project_id: str
    role: Role
    created_by: str  # account id
    accepted_by: Optional[str]  # account id or None
    created_at: float
    expires_at: Optional[float]  # None = 永不过期

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        return d
