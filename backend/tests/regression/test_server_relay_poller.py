"""Local Server relay poller contract (WB-361)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import server_sync  # noqa: E402
from agent import scheduler  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402


class ServerRelayPollerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()
        scheduler._relay_tasks.clear()

    def tearDown(self) -> None:
        scheduler._relay_tasks.clear()
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_device_target_is_stable_and_opaque(self) -> None:
        first = server_sync.relay_device_id()
        second = server_sync.relay_device_id()
        self.assertEqual(first, second)
        self.assertRegex(first, r"^device-[0-9a-f-]{36}$")

    async def test_leased_event_drives_webhook_fire_then_acks_terminal_result(self) -> None:
        event = {
            "id": "relay-1", "event_key": "build-1", "automation_id": "auto-1",
            "lease_token": "lease-secret", "payload": {"status": "failed"},
        }
        auto = SimpleNamespace(id="auto-1", trigger_kind="webhook", enabled=True)
        fire = SimpleNamespace(id="fire-1")
        final = SimpleNamespace(status="succeeded", error_code=None, error_message=None)
        with (
            patch.object(scheduler.db, "get_automation", return_value=auto),
            patch.object(scheduler, "run_webhook", AsyncMock(return_value=(fire, True))) as run,
            patch.object(scheduler.db, "get_automation_fire", return_value=final),
            patch.object(scheduler.server_client, "acknowledge_relay_event", return_value=True) as ack,
        ):
            await scheduler._process_relay_event(
                "owner-1", "account-token", "device-owner-1", event,
            )
        payload = run.await_args.args[3]
        self.assertEqual("relay-1", payload["server_relay"]["event_id"])
        self.assertEqual({"status": "failed"}, payload["payload"])
        self.assertEqual("succeeded", ack.call_args.kwargs["status"])
        self.assertEqual("lease-secret", ack.call_args.kwargs["lease_token"])

    async def test_wrong_local_automation_fails_closed(self) -> None:
        event = {
            "id": "relay-2", "automation_id": "other-owner-auto",
            "lease_token": "lease-secret", "payload": {},
        }
        with (
            patch.object(scheduler.db, "get_automation", return_value=None),
            patch.object(scheduler.server_client, "acknowledge_relay_event", return_value=True) as ack,
        ):
            await scheduler._process_relay_event(
                "owner-1", "account-token", "device-owner-1", event,
            )
        self.assertEqual("failed", ack.call_args.kwargs["status"])
        self.assertEqual("automation_unavailable", ack.call_args.kwargs["error_code"])


if __name__ == "__main__":
    unittest.main()
