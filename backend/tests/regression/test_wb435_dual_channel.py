"""WB-435 Desktop business/Local Agent channel boundary regressions."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import local_agent_core
import local_agent_ipc
import local_agent_store
from config import settings
from routers import chat as chat_router
from routers.chat import ChatBody
from storage.models import Role, User


class DesktopDualChannelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_local_path = settings.LOCAL_AGENT_DB_PATH
        self.old_server_url = settings.AGENTMATE_SERVER_URL
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "local-agent.db"
        settings.AGENTMATE_SERVER_URL = "https://server.example.test"
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        local_agent_ipc.install_token("b" * 64)

    def tearDown(self) -> None:
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        local_agent_ipc.clear_token()
        settings.LOCAL_AGENT_DB_PATH = self.old_local_path
        settings.AGENTMATE_SERVER_URL = self.old_server_url
        self.temp.cleanup()

    def test_local_status_bootstraps_only_non_secret_server_origin(self) -> None:
        response = TestClient(local_agent_core.app).get(
            "/api/local-agent/status", headers={"X-AgentMate-IPC-Token": "b" * 64},
        )
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("https://server.example.test", payload["server_api_url"])
        self.assertNotIn("token", response.text.lower())
        self.assertNotIn("credential", response.text.lower())

    def test_frontend_has_distinct_clients_and_no_legacy_server_proxy(self) -> None:
        repository = Path(__file__).resolve().parents[3]
        channels = (repository / "src" / "lib" / "channels.ts").read_text(encoding="utf-8")
        api = (repository / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        sse = (repository / "src" / "lib" / "sse.ts").read_text(encoding="utf-8")
        app_shell = (repository / "src" / "App.tsx").read_text(encoding="utf-8")
        banner = (repository / "src" / "components" / "layout" / "ConnectivityBanner.tsx").read_text(encoding="utf-8")

        self.assertIn("VITE_SERVER_API_BASE", channels)
        self.assertIn("VITE_LOCAL_API_BASE", channels)
        self.assertIn("serverGetAll", channels)
        self.assertIn("serverGet", api)
        self.assertIn("serverSend", api)
        self.assertIn("value.account ?? value.user", api)
        self.assertNotIn("'/server/", api)
        self.assertIn("prepareServerTurn", sse)
        self.assertIn("followServerRun", sse)
        self.assertIn("commitRunArtifacts", sse)
        self.assertIn("after_epoch", sse)
        self.assertNotIn("history.slice(-200)", sse)
        self.assertIn("automation_id: opts.automationId", sse)
        self.assertIn("case 'automation':", app_shell)
        self.assertIn("content = <ConsoleHandoffView />", app_shell)
        self.assertFalse((repository / "src" / "views" / "AutomationView.tsx").exists())
        self.assertFalse((repository / "src" / "stores" / "automationStore.ts").exists())
        self.assertIn("Server 离线", banner)
        self.assertIn("Local Agent 离线", banner)
        self.assertIn("等待 Server ACK", banner)
        self.assertIn("协议不兼容", banner)

    def test_server_history_is_bounded_context_input_not_a_local_authority(self) -> None:
        body = ChatBody(
            text="continue",
            history=[{"role": "user", "content": "older"}, {"role": "assistant", "content": "answer"}],
        )
        self.assertEqual(2, len(body.history))
        with self.assertRaises(Exception):
            ChatBody(text="continue", history=[{"role": "user", "content": "x"}] * 201)

    def test_server_project_context_is_transient_and_viewer_fails_closed(self) -> None:
        user = User(id="account-1", name="Owner", role=Role.OWNER)
        remote = {
            "id": "project-1", "name": "Cloud project", "owner_id": user.id,
            "instruction": "Server-owned instructions", "role": "Owner",
            "connectors": ["github"], "experts": [], "skills": ["review"],
            "knowledge_ids": [], "org_id": "org-1",
        }
        with (
            patch.object(chat_router.db, "get_server_identity", return_value="server-token"),
            patch.object(chat_router.server_client, "get_project", return_value=remote) as fetch,
        ):
            project = asyncio.run(chat_router._load_server_project(user, "project-1"))
        fetch.assert_called_once_with("server-token", "project-1")
        self.assertEqual("server", project.origin)
        self.assertEqual("Server-owned instructions", project.instruction)

        remote["role"] = "Viewer"
        with (
            patch.object(chat_router.db, "get_server_identity", return_value="server-token"),
            patch.object(chat_router.server_client, "get_project", return_value=remote),
            self.assertRaises(HTTPException) as denied,
        ):
            asyncio.run(chat_router._load_server_project(user, "project-1"))
        self.assertEqual(403, denied.exception.status_code)


if __name__ == "__main__":
    unittest.main()
