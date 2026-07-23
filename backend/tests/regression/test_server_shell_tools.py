"""Server-downlinked native policy and cross-platform shell tool regression (WB-319)."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.sandbox import use_root  # noqa: E402
from agent.server_tools import build_shell_tools, platform_key  # noqa: E402
from agent.skills import _resolve_tools  # noqa: E402
from agent.tools import ToolOutcome, base_tools  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402


def native(name: str, *, enabled: bool = True) -> dict:
    return {
        "name": name, "label": name, "implementation_type": "native",
        "exposure": "skill", "bindable": True, "enabled": enabled,
        "permissions": ["workspace.read"], "parameters": {}, "scripts": {},
        "timeout_seconds": 30, "output_limit": 65536,
    }


def shell_tool(**overrides: object) -> dict:
    value = {
        "name": "server_echo", "label": "Server Echo", "description": "Echo JSON input",
        "implementation_type": "shell", "exposure": "skill", "bindable": True, "enabled": True,
        "permissions": ["process.execute"], "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "fail": {"type": "boolean"}},
            "required": ["name"],
        },
        "scripts": {
            "windows": (
                "$raw = [Console]::In.ReadToEnd()\n"
                "$payload = $raw | ConvertFrom-Json\n"
                "if ($payload.fail) { [Console]::Error.WriteLine('broken'); exit 7 }\n"
                "Write-Output ('windows:' + $payload.name)\n"
            ),
            "linux": "payload=$(cat)\nprintf 'linux:%s' \"$payload\"\n",
            "macos": "payload=$(cat)\nprintf 'macos:%s' \"$payload\"\n",
        },
        "timeout_seconds": 5, "output_limit": 65536,
    }
    value.update(overrides)
    return value


class ServerShellToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        db._local = threading.local()
        db.init_db()
        use_root(Path(self.tmp.name) / "workspace")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_snapshot_is_validated_atomically_and_native_policy_is_applied(self) -> None:
        result = db.replace_server_tool_catalog([native("read_file"), shell_tool()])
        self.assertEqual(2, result["inserted"])
        self.assertTrue(result["accepted"])
        self.assertEqual(["read_file"], [tool.name for tool in base_tools()])
        self.assertEqual(["server_echo"], [tool.name for tool in _resolve_tools(["server_echo"])])

        rejected = db.replace_server_tool_catalog([{
            **shell_tool(), "scripts": {"freebsd": "echo unsafe"},
        }])
        self.assertFalse(rejected["accepted"])
        self.assertTrue(rejected["preserved"])
        self.assertEqual({"read_file", "server_echo"}, {item["name"] for item in db.list_server_tool_catalog()})

    def test_platform_selection_maps_darwin_to_macos_without_cross_executing(self) -> None:
        db.replace_server_tool_catalog([shell_tool()])
        self.assertEqual("macos", platform_key("Darwin"))
        with patch("agent.server_tools._run_shell_tool", return_value=ToolOutcome(text="ok")) as runner:
            linux = build_shell_tools("Linux")[0]
            outcome = linux.run({"name": "value"})
        self.assertEqual("ok", outcome.text)
        self.assertEqual("linux", runner.call_args.args[1])
        self.assertIn("printf 'linux:", runner.call_args.args[2])

    @unittest.skipUnless(sys.platform == "win32", "PowerShell execution is Windows-specific")
    def test_windows_executes_pwsh_with_json_stdin_and_reports_nonzero(self) -> None:
        db.replace_server_tool_catalog([shell_tool()])
        tool = build_shell_tools("Windows")[0]
        injected = 'a\"; Write-Output HACK'
        success = tool.run({"name": injected, "fail": False})
        self.assertEqual(f"windows:{injected}", success.text)
        failed = tool.run({"name": "x", "fail": True})
        self.assertIn("退出码 7", failed.text)
        self.assertIn("broken", failed.text)

        db.replace_server_tool_catalog([shell_tool(
            scripts={"windows": "Write-Output ('x' * 2048)"},
            output_limit=1024,
        )])
        truncated = build_shell_tools("Windows")[0].run({})
        self.assertIn("输出已截断", truncated.text)

        db.replace_server_tool_catalog([shell_tool(
            scripts={"windows": "Start-Sleep -Seconds 2"},
            timeout_seconds=1,
        )])
        timed_out = build_shell_tools("Windows")[0].run({})
        self.assertIn("执行超时（1 秒）", timed_out.text)


if __name__ == "__main__":
    unittest.main()
