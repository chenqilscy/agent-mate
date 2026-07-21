"""Structured permission and killable execution policy regression coverage (WB-248)."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import tempfile
import time
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import security
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
            task = asyncio.create_task(execute_tool(
                run_command, {"command": self._late_write_command(target.name)}, stop,
            ))
            await asyncio.sleep(0.2)
            stop.set()
            await task

        with self.assertRaises(ToolExecutionCancelled):
            asyncio.run(scenario())
        time.sleep(1.5)
        self.assertFalse(target.exists())

    def test_timeout_kills_isolated_process_tree_before_late_write(self) -> None:
        target = self.workspace / "timed-out.txt"
        policy = replace(run_command, timeout_seconds=0.2)

        async def scenario() -> None:
            await execute_tool(
                policy, {"command": self._late_write_command(target.name)}, asyncio.Event(),
            )

        with self.assertRaises(ToolExecutionTimeout):
            asyncio.run(scenario())
        time.sleep(1.5)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
