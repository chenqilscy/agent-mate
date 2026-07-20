"""App 本地连接器运行目录与 Server 推荐位契约（WB-220）。"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
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

    def test_server_definition_overrides_runtime_without_secret_values(self) -> None:
        result = db.replace_server_connector_catalog([
            {"slug": "github", "name": "GitHub", "icon": "🐙", "desc": "Server 定义", "status": "tok",
             "launch": {"command": "pnpm", "args": ["mcp-github"],
                        "secret_env": {"ACCESS_TOKEN": "GITHUB_TOKEN"}, "requires": ["GITHUB_TOKEN"]}},
            {"slug": "bad slug", "name": "bad", "status": "rdy", "launch": {"command": "x"}},
        ])
        self.assertEqual({"inserted": 1, "skipped": 1}, result)
        self.assertEqual("pnpm", db.connector_specs()["GitHub"]["command"])
        self.assertNotIn("actual-secret", str(db.connector_specs()))
        card = next(c for c in db.connector_catalog_specs() if c["slug"] == "github")
        self.assertEqual("Server 定义", card["description"])

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
