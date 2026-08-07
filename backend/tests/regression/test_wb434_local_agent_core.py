"""WB-434 Local Agent-only DB, protected IPC and Server Run completion gates."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import local_agent_core
import local_agent_ipc
import local_agent_store
import run_transport
from config import settings


class LocalAgentCoreBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_local_path = settings.LOCAL_AGENT_DB_PATH
        self.old_business_path = settings.DB_PATH
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "local-agent.db"
        settings.DB_PATH = Path(self.temp.name) / "business.db"
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        local_agent_ipc.install_token("a" * 64)
        self.client = TestClient(local_agent_core.app)
        self.headers = {"X-AgentMate-IPC-Token": "a" * 64}
        self.owner_id = "owner-wb434"

    def tearDown(self) -> None:
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        local_agent_ipc.clear_token()
        settings.LOCAL_AGENT_DB_PATH = self.old_local_path
        settings.DB_PATH = self.old_business_path
        self.temp.cleanup()

    def test_core_has_only_authenticated_local_agent_routes_and_no_business_db(self) -> None:
        self.assertEqual(401, self.client.get("/api/local-agent/status").status_code)
        response = self.client.get("/api/local-agent/status", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual("local-agent-core", response.json()["service"])
        self.assertNotIn("token", response.text.lower())

        for path in (
            "/api/projects", "/api/sessions", "/api/runs", "/api/automations",
            "/api/auth/login", "/docs", "/openapi.json",
        ):
            self.assertEqual(404, self.client.get(path, headers=self.headers).status_code, path)

        self.assertFalse(settings.DB_PATH.exists(), "Core must not create the legacy business DB")
        with sqlite3.connect(settings.LOCAL_AGENT_DB_PATH) as conn:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        self.assertEqual({
            "local_agent_schema", "device_settings", "device_secrets",
            "server_identities", "run_transport_leases", "run_event_wal",
        }, tables)
        self.assertEqual("127.0.0.1", local_agent_core.bind_host())

        local_agent_ipc.clear_token()
        self.assertEqual(
            503, self.client.get("/api/local-agent/status", headers=self.headers).status_code,
        )

    def test_non_loopback_client_is_rejected_before_route_dispatch(self) -> None:
        sent: list[dict] = []

        async def unreachable(_scope, _receive, _send) -> None:
            raise AssertionError("non-loopback request reached the Core router")

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            sent.append(message)

        scope = {
            "type": "http", "method": "GET", "path": "/api/local-agent/status",
            "headers": [(b"x-agentmate-ipc-token", b"a" * 64)],
            "client": ("192.168.1.20", 50000),
        }
        asyncio.run(local_agent_core.LocalAgentIpcMiddleware(unreachable)(scope, receive, send))
        self.assertEqual(403, sent[0]["status"])

    def test_tauri_bootstraps_ipc_over_stdin_and_frontend_never_receives_token(self) -> None:
        repository = Path(__file__).resolve().parents[3]
        rust = (repository / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        platform = (repository / "src" / "platform" / "index.ts").read_text(encoding="utf-8")
        self.assertIn('command.arg("--ipc-token-stdin")', rust)
        self.assertIn("child.write(bootstrap.as_bytes())", rust)
        self.assertNotIn("AGENTMATE_LOCAL_AGENT_IPC_TOKEN", rust)
        self.assertNotIn("X-AgentMate-IPC-Token", platform)
        self.assertNotIn("ipc_token", platform.lower())

    def test_register_claim_complete_and_ack_without_business_storage(self) -> None:
        user_token = "server-user-token-wb434"
        with patch(
            "server_client.verify_token_state",
            return_value=("valid", {"id": self.owner_id, "_token_expires_at": 9999999999}),
        ):
            bound = self.client.put(
                "/api/local-agent/identity", headers=self.headers,
                json={"owner_id": self.owner_id, "server_token": user_token},
            )
        self.assertEqual(200, bound.status_code, bound.text)
        self.assertNotIn(user_token, bound.text)

        lease = {
            "lease_id": "lease-wb434", "lease_epoch": 1, "expires_at": 9999999999,
            "ack_high_water": 0, "run": {"id": "run-wb434", "input": "execute"},
        }
        with (
            patch("server_client.register_run_device", return_value={
                "challenge": {"challenge_id": "challenge-wb434", "challenge": "sign-me"},
            }),
            patch("server_client.verify_run_device", return_value={
                "device_token": "device-token-wb434", "expires_at": 9999999999,
            }),
            patch("server_client.device_post", return_value=(200, {"lease": lease})),
        ):
            claimed = self.client.post(
                "/api/local-agent/runs/claim", headers=self.headers,
                json={"owner_id": self.owner_id, "lease_seconds": 30},
            )
        self.assertEqual(200, claimed.status_code, claimed.text)
        self.assertEqual("run-wb434", claimed.json()["run"]["id"])

        for event_type, payload in (
            ("run.started", {}), ("run.completed", {"summary": "done"}),
        ):
            event = self.client.post(
                "/api/local-agent/runs/run-wb434/events", headers=self.headers,
                json={"owner_id": self.owner_id, "type": event_type, "payload": payload},
            )
            self.assertEqual(200, event.status_code, event.text)

        with patch(
            "server_client.device_post",
            return_value=(200, {"ack_high_water": 2, "commands": []}),
        ):
            flushed = self.client.post(
                "/api/local-agent/runs/flush", headers=self.headers,
                json={"owner_id": self.owner_id},
            )
        self.assertEqual({"acknowledged": 2, "pending": 0}, flushed.json())
        self.assertFalse(settings.DB_PATH.exists())

        raw_db = settings.LOCAL_AGENT_DB_PATH.read_bytes()
        self.assertNotIn(user_token.encode(), raw_db)
        self.assertNotIn(b"device-token-wb434", raw_db)
        self.assertNotIn(b"sign-me", raw_db)

    def test_ipc_rejects_cross_owner_event_and_secret_payload(self) -> None:
        local_agent_store.init_db()
        run_transport.record_lease(self.owner_id, {
            "lease_id": "lease-wb434", "lease_epoch": 1, "expires_at": 9999999999,
            "ack_high_water": 0, "run": {"id": "run-wb434"},
        })
        wrong_owner = self.client.post(
            "/api/local-agent/runs/run-wb434/events", headers=self.headers,
            json={"owner_id": "owner-attacker", "type": "run.completed", "payload": {}},
        )
        self.assertEqual(404, wrong_owner.status_code)
        secret = self.client.post(
            "/api/local-agent/runs/run-wb434/events", headers=self.headers,
            json={
                "owner_id": self.owner_id, "type": "run.checkpoint",
                "payload": {"api_key": "must-not-enter-wal"},
            },
        )
        self.assertEqual(400, secret.status_code)
        self.assertNotIn(b"must-not-enter-wal", settings.LOCAL_AGENT_DB_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
