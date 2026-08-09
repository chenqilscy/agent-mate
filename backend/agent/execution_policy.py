"""Fail-closed runtime authorization for built-in and MCP tool calls (WB-374)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from threading import RLock
from typing import Any, Literal

from agent import security

ExecutionSource = Literal["interactive", "background", "external"]

# These permissions are intentionally explicit and stable because they are stored
# in Automation records. Adding a new privileged permission does not grant it to
# existing automations: unknown write/dynamic permissions remain restricted.
PREAUTHORIZABLE_PERMISSIONS = frozenset({
    "workspace.write", "project.write", "knowledge.write", "skill.manage",
    "network.read", "network.write", "browser.state", "connector.call",
    "external.dynamic", "process.execute", "host.unrestricted",
    "network.unrestricted", "run.plan.write",
})

INTERACTIVE_CONFIRM_PERMISSIONS = frozenset({
    "process.execute", "host.unrestricted", "network.unrestricted",
})

ALLOW_ONCE_ANSWER = "允许一次"
ALLOW_SESSION_ANSWER = "当前会话内全部允许"
DENY_ANSWER = "拒绝"
TOOL_AUTHORIZATION_OPTIONS = (
    ALLOW_ONCE_ANSWER, ALLOW_SESSION_ANSWER, DENY_ANSWER,
)

# Session grants are deliberately process-local. A user's explicit temporary
# approval survives later Runs in the same chat Session, but never becomes a
# durable account/project permission and disappears on backend restart.
_session_grants: dict[tuple[str, str], frozenset[str]] = {}
_session_grants_lock = RLock()


class ToolAuthorizationDenied(PermissionError):
    pass


def _call_key(tool_name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{tool_name}\n{payload}".encode("utf-8")).hexdigest()


def _restricted_for_background(permission: str, *, external: bool) -> bool:
    if permission in PREAUTHORIZABLE_PERMISSIONS:
        return True
    if permission.endswith(".write") or permission.endswith(".manage"):
        return True
    # External input must not get an unclassified dynamic/network authority merely
    # because a connector or new tool was added later.
    return external and (
        permission.startswith("network.")
        or permission.startswith("connector.")
        or permission.startswith("external.")
    )


def session_granted_permissions(owner_id: str, session_id: str) -> frozenset[str]:
    with _session_grants_lock:
        return _session_grants.get((owner_id, session_id), frozenset())


def clear_session_authorization(owner_id: str, session_id: str) -> None:
    with _session_grants_lock:
        _session_grants.pop((owner_id, session_id), None)


@dataclass
class ExecutionAuthorization:
    owner_id: str
    session_id: str | None = None
    source: ExecutionSource = "interactive"
    preauthorized_permissions: frozenset[str] = frozenset()
    _approved_calls: set[str] = field(default_factory=set)

    def decision(
        self, tool_name: str, args: dict[str, Any], permissions: tuple[str, ...] | list[str],
    ) -> Literal["allow", "confirm", "deny"]:
        required = frozenset(str(item) for item in permissions if str(item))
        if self.source == "interactive":
            high_risk = required & INTERACTIVE_CONFIRM_PERMISSIONS
            if high_risk:
                session_grants = (
                    session_granted_permissions(self.owner_id, self.session_id)
                    if self.session_id else frozenset()
                )
                if high_risk <= session_grants:
                    return "allow"
                return "allow" if _call_key(tool_name, args) in self._approved_calls else "confirm"
            return "allow"
        restricted = {
            item for item in required
            if _restricted_for_background(item, external=self.source == "external")
        }
        return "allow" if restricted <= self.preauthorized_permissions else "deny"

    def tool_available(self, permissions: tuple[str, ...] | list[str]) -> bool:
        # Interactive tools remain discoverable so an exact-call confirmation can
        # be requested. Background tools with insufficient authority are omitted
        # from the model schema as well as rejected at the execution boundary.
        if self.source == "interactive":
            return True
        return self.decision("__schema__", {}, permissions) == "allow"

    def approve_once(self, tool_name: str, args: dict[str, Any]) -> None:
        self._approved_calls.add(_call_key(tool_name, args))

    def approve_for_session(self, permissions: tuple[str, ...] | list[str]) -> None:
        if self.source != "interactive" or not self.session_id:
            raise ToolAuthorizationDenied("session authorization requires an interactive session")
        granted = frozenset(str(item) for item in permissions if str(item))
        granted &= INTERACTIVE_CONFIRM_PERMISSIONS
        if not granted:
            return
        key = (self.owner_id, self.session_id)
        with _session_grants_lock:
            _session_grants[key] = _session_grants.get(key, frozenset()) | granted

    def enforce(
        self, tool_name: str, args: dict[str, Any], permissions: tuple[str, ...] | list[str],
    ) -> None:
        decision = self.decision(tool_name, args, permissions)
        detail = json.dumps(
            {"source": self.source, "tool": tool_name, "permissions": sorted(permissions)},
            ensure_ascii=False, sort_keys=True,
        )
        if decision != "allow":
            security.audit(self.owner_id, "tool_authorization", detail, decision)
            raise ToolAuthorizationDenied(
                f"tool authorization {decision}: {tool_name} ({self.source})"
            )
        # For high-risk calls, inability to persist the authorization audit is a
        # security failure rather than a reason to execute without evidence.
        high_risk = bool(set(permissions) & INTERACTIVE_CONFIRM_PERMISSIONS)
        if not security.audit(self.owner_id, "tool_authorization", detail, "allowed") and high_risk:
            raise ToolAuthorizationDenied(f"authorization audit unavailable: {tool_name}")
