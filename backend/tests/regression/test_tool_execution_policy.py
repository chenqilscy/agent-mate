"""Structured permission and killable execution policy regression coverage (WB-248)."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import tempfile
import time
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import security
from agent.execution_policy import ExecutionAuthorization, ToolAuthorizationDenied
from agent.sandbox import use_root
from agent.tool_execution import ToolExecutionCancelled, ToolExecutionTimeout, execute_tool
from agent.tools import base_tools, run_command


class ToolExecutionPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        use_root(self.workspace)
        security.set_security_context(None)

    def tearDown(self) -> None:
        security.set_security_context(None)
        self.tmp.cleanup()

    def _late_write_command(self, path: str, delay_ms: int = 1200) -> str:
        return (
            'powershell.exe -NoProfile -Command '
            f'"Start-Sleep -Milliseconds {delay_ms}; Set-Content -LiteralPath \'{path}\' -Value late"'
        )

    def _authorized(self, tool, args):
        auth = ExecutionAuthorization(owner_id="test-user")
        auth.approve_once(tool.name, args)
        return auth

    def test_every_builtin_tool_declares_permissions_and_deadline(self) -> None:
        for tool in base_tools(False):
            self.assertTrue(tool.permissions, tool.name)
            self.assertGreater(tool.timeout_seconds, 0, tool.name)
        self.assertEqual("subprocess", run_command.isolation)
        self.assertIn("process.execute", run_command.permissions)
        self.assertIn("host.unrestricted", run_command.permissions)

    def test_cancel_kills_isolated_process_tree_before_late_write(self) -> None:
        target = self.workspace / "cancelled.txt"

        async def scenario() -> None:
            stop = asyncio.Event()
            args = {"command": self._late_write_command(target.name)}
            task = asyncio.create_task(execute_tool(
                run_command, args, stop, authorization=self._authorized(run_command, args),
            ))
            await asyncio.sleep(0.2)
            stop.set()
            await task

        with patch.object(security, "audit", return_value=True):
            with self.assertRaises(ToolExecutionCancelled):
                asyncio.run(scenario())
        time.sleep(1.5)
        self.assertFalse(target.exists())

    def test_timeout_kills_isolated_process_tree_before_late_write(self) -> None:
        target = self.workspace / "timed-out.txt"
        policy = replace(run_command, timeout_seconds=0.2)

        async def scenario() -> None:
            args = {"command": self._late_write_command(target.name)}
            await execute_tool(
                policy, args, asyncio.Event(), authorization=self._authorized(policy, args),
            )

        with patch.object(security, "audit", return_value=True):
            with self.assertRaises(ToolExecutionTimeout):
                asyncio.run(scenario())
        time.sleep(1.5)
        self.assertFalse(target.exists())

    def test_background_high_risk_tool_requires_exact_preauthorization(self) -> None:
        args = {"command": "echo safe"}
        denied = ExecutionAuthorization(owner_id="owner", source="external")
        with self.assertRaises(ToolAuthorizationDenied):
            denied.enforce(run_command.name, args, run_command.permissions)
        allowed = ExecutionAuthorization(
            owner_id="owner", source="external",
            preauthorized_permissions=frozenset({
                "workspace.write", "process.execute", "host.unrestricted", "network.unrestricted",
            }),
        )
        with patch.object(security, "audit", return_value=True):
            allowed.enforce(run_command.name, args, run_command.permissions)

    def test_thread_timeout_waits_for_side_effect_boundary_before_reporting(self) -> None:
        target = self.workspace / "thread-finished.txt"

        def finish_later(_args):
            time.sleep(0.15)
            target.write_text("done", encoding="utf-8")
            from agent.tools import ToolOutcome
            return ToolOutcome(text="done")

        from agent.tools import Tool
        tool = Tool(
            name="bounded_write", description="test", parameters={"type": "object"},
            pre=lambda _a: None, run=finish_later, permissions=("workspace.write",),
            timeout_seconds=0.05,
        )
        started = time.monotonic()
        with self.assertRaises(ToolExecutionTimeout):
            asyncio.run(execute_tool(
                tool, {}, asyncio.Event(),
                authorization=ExecutionAuthorization(owner_id="owner"),
            ))
        self.assertGreaterEqual(time.monotonic() - started, 0.14)
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
