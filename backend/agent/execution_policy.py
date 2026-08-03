"""Fail-closed runtime authorization for built-in and MCP tool calls (WB-374)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
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


@dataclass
class ExecutionAuthorization:
    owner_id: str
    source: ExecutionSource = "interactive"
    preauthorized_permissions: frozenset[str] = frozenset()
    _approved_calls: set[str] = field(default_factory=set)

    def decision(
        self, tool_name: str, args: dict[str, Any], permissions: tuple[str, ...] | list[str],
    ) -> Literal["allow", "confirm", "deny"]:
        required = frozenset(str(item) for item in permissions if str(item))
        if self.source == "interactive":
            if required & INTERACTIVE_CONFIRM_PERMISSIONS:
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

