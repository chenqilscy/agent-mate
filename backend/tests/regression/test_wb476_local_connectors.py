"""WB-476: custom MCP definitions and credentials remain owner-local and health-gated."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import local_agent_store  # noqa: E402
from agent import mcp_client  # noqa: E402
from config import settings  # noqa: E402


class LocalConnectorStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.LOCAL_AGENT_DB_PATH
        self.catalog = patch("storage.db.connector_specs", side_effect=lambda: {})
        self.catalog.start()
        local_agent_store.close_thread_connection()
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "core.db"

    def tearDown(self) -> None:
        self.catalog.stop()
        local_agent_store.close_thread_connection()
        settings.LOCAL_AGENT_DB_PATH = self.old_path
        self.temp.cleanup()

    def test_instance_and_secret_are_owner_scoped_and_never_returned(self) -> None:
        item = local_agent_store.save_connector_instance(
            "owner-a", instance_id="instance-1", name="Private MCP", transport="stdio",
            command="mcp-server", args=["--stdio"], secret_keys=["API_TOKEN"],
        )
        local_agent_store.set_connector_secret("owner-a", item["id"], "API_TOKEN", "super-secret")
        visible = local_agent_store.get_connector_instance("owner-a", item["id"])
        self.assertEqual({"API_TOKEN": True}, visible["has_secrets"])
        self.assertNotIn("super-secret", repr(visible))
        self.assertIsNone(local_agent_store.get_connector_instance("owner-b", item["id"]))
        self.assertIn("Private MCP", mcp_client.connector_specs("owner-a"))
        self.assertNotIn("Private MCP", mcp_client.connector_specs("owner-b"))

    def test_runtime_rejects_unhealthy_custom_instance_before_spawn(self) -> None:
        local_agent_store.save_connector_instance(
            "owner-a", instance_id="instance-2", name="Untested MCP", transport="stdio",
            command="does-not-run", secret_keys=[],
        )
        async def exercise():
            tools, stack, skipped = await mcp_client.open_connectors(
                ["Untested MCP"], owner_id="owner-a"
            )
            await stack.aclose()
            return tools, skipped

        with patch("agent.mcp_client._resolve_command") as resolve:
            tools, skipped = __import__("asyncio").run(exercise())
        self.assertEqual([], tools)
        self.assertEqual("本机连接器尚未通过连通测试", skipped[0]["reason"])
        resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
