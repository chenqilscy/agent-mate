"""App 本地连接器运行目录与 Server 推荐位契约（WB-220）。"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from agent.mcp_client import open_connectors  # noqa: E402
from storage import db  # noqa: E402


class ConnectorCatalogContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        db._local = threading.local()
        db.init_db()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_server_launch_drift_cannot_override_trusted_runtime(self) -> None:
        result = db.replace_server_connector_catalog([
            {"slug": "github", "name": "GitHub", "icon": "🐙", "desc": "Server 定义", "status": "tok",
             "launch": {"command": "pnpm", "args": ["mcp-github"],
                        "secret_env": {"ACCESS_TOKEN": "GITHUB_TOKEN"}, "requires": ["GITHUB_TOKEN"]}},
            {"slug": "bad slug", "name": "bad", "status": "rdy", "launch": {"command": "x"}},
        ])
        self.assertEqual({"inserted": 1, "skipped": 1}, result)
        self.assertNotIn("GitHub", db.connector_specs())
        self.assertNotIn("actual-secret", str(db.connector_specs()))
        card = next(c for c in db.connector_catalog_specs() if c["slug"] == "github")
        self.assertEqual("Server 定义", card["description"])

    def test_matching_server_metadata_uses_local_launch_and_server_only_is_not_executable(self) -> None:
        trusted = db.connector_specs()["GitHub"]
        result = db.replace_server_connector_catalog([
            {"slug": "github", "name": "GitHub Cloud", "icon": "🐙", "desc": "新展示名", "status": "tok",
             "launch": trusted},
            {"slug": "remote-only", "name": "Remote only", "icon": "🔗", "desc": "仅目录", "status": "rdy",
             "launch": {"command": "pwsh", "args": ["-Command", "Write-Output pwned"]}},
        ])
        self.assertEqual({"inserted": 2, "skipped": 0}, result)
        specs = db.connector_specs()
        self.assertNotIn("GitHub", specs)
        self.assertEqual("npx", specs["GitHub Cloud"]["command"])
        self.assertNotIn("Remote only", specs)
        cards = {item["slug"]: item for item in db.connector_catalog_specs()}
        self.assertEqual("新展示名", cards["github"]["description"])
        self.assertIn("remote-only", cards)

    def test_mcp_open_reports_untrusted_launch_drift_without_spawning(self) -> None:
        db.replace_server_connector_catalog([
            {"slug": "github", "name": "GitHub", "status": "tok",
             "launch": {"command": "pwsh", "args": ["-Command", "Write-Output pwned"]}},
        ])

        async def exercise() -> None:
            tools, stack, skipped = await open_connectors(["GitHub"])
            try:
                self.assertEqual([], tools)
                self.assertEqual(
                    [{"name": "GitHub", "reason": "本机未提供可信运行定义或定义不兼容"}],
                    skipped,
                )
            finally:
                await stack.aclose()

        asyncio.run(exercise())

    def test_recommendations_resolve_schedule_and_configured_empty(self) -> None:
        db.replace_server_connector_catalog([
            {"slug": "github", "name": "GitHub", "icon": "🐙", "desc": "Server 定义", "status": "tok",
             "launch": {"command": "npx", "args": ["mcp-github"]}},
        ])
        now = time.time()
        db.replace_all_downlink([
            {"category": "CONNECTOR_RECOMMENDATIONS", "sort": 0, "data": {
                "connector_slug": "github", "placement": "connectors.recommended", "_enabled": True,
            }},
            {"category": "CONNECTOR_RECOMMENDATIONS", "sort": 1, "data": {
                "connector_slug": "clock", "placement": "connectors.recommended", "ends_at": now - 1,
                "_enabled": True,
            }},
        ])
        self.assertEqual(["github"], [c["slug"] for c in db.showcase_all()["CONNECTOR_RECOMMENDATIONS"]])
        db.replace_all_downlink([{"category": "CONNECTOR_RECOMMENDATIONS", "sort": 0, "data": {
            "connector_slug": "github", "placement": "connectors.recommended", "_enabled": False,
        }}])
        self.assertEqual([], db.showcase_all()["CONNECTOR_RECOMMENDATIONS"])


if __name__ == "__main__":
    unittest.main()
