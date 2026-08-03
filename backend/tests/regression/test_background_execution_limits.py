"""Shared background Agent and relay admission control (WB-369)."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import background_limits, scheduler  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class BackgroundExecutionLimitsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_global = settings.BACKGROUND_AGENT_MAX_CONCURRENCY
        self.old_owner = settings.BACKGROUND_AGENT_PER_OWNER_CONCURRENCY
        self.old_relay = settings.RELAY_MAX_IN_FLIGHT
        self.old_relay_owner = settings.RELAY_PER_OWNER_MAX_IN_FLIGHT
        settings.DB_PATH = Path(self.temp.name) / "agentmate.db"
        settings.BACKGROUND_AGENT_MAX_CONCURRENCY = 2
        settings.BACKGROUND_AGENT_PER_OWNER_CONCURRENCY = 1
        settings.RELAY_MAX_IN_FLIGHT = 2
        settings.RELAY_PER_OWNER_MAX_IN_FLIGHT = 1
        db._local = threading.local()
        db.init_db()
        scheduler._running.clear()
        scheduler._fire_tasks.clear()
        scheduler._fire_owners.clear()
        scheduler._relay_tasks.clear()
        scheduler._relay_owners.clear()

    async def asyncTearDown(self) -> None:
        await scheduler.stop()
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        settings.BACKGROUND_AGENT_MAX_CONCURRENCY = self.old_global
        settings.BACKGROUND_AGENT_PER_OWNER_CONCURRENCY = self.old_owner
        settings.RELAY_MAX_IN_FLIGHT = self.old_relay
        settings.RELAY_PER_OWNER_MAX_IN_FLIGHT = self.old_relay_owner
        db._local = threading.local()
        self.temp.cleanup()

    async def test_global_and_owner_limits_apply_to_agent_slots(self) -> None:
        entered: list[str] = []
        release = asyncio.Event()

        async def run(owner: str) -> None:
            async with background_limits.slot(owner):
                entered.append(owner)
                await release.wait()

        tasks = [
            asyncio.create_task(run("owner-a")),
            asyncio.create_task(run("owner-a")),
            asyncio.create_task(run("owner-b")),
        ]
        await asyncio.sleep(0.05)
        self.assertEqual(2, len(entered))
        self.assertEqual(1, entered.count("owner-a"))
        self.assertEqual(1, entered.count("owner-b"))
        self.assertEqual(1, background_limits.snapshot()["waiting"])
        release.set()
        await asyncio.gather(*tasks)
        self.assertEqual(0, background_limits.snapshot()["active"])

    async def test_scheduler_leaves_excess_fires_durable_and_relay_pulls_only_capacity(self) -> None:
        auto = db.create_automation(owner_id=LOCAL_USER_ID, name="bounded", prompt="run")
        other = db.create_user(name="other-owner", password="pw")
        other_auto = db.create_automation(owner_id=other.id, name="other", prompt="run")
        fires = [
            db.create_automation_fire(
                automation_id=auto.id, owner_id=auto.owner_id, fire_key=f"manual:{index}",
                trigger_kind="manual", planned_at=0, max_attempts=1,
            )[0]
            for index in range(2)
        ]
        fires.append(db.create_automation_fire(
            automation_id=other_auto.id, owner_id=other.id, fire_key="manual:other",
            trigger_kind="manual", planned_at=0, max_attempts=1,
        )[0])
        blocker = asyncio.Event()

        async def blocked(_fire_id: str) -> None:
            await blocker.wait()

        with patch.object(scheduler, "_execute_fire", side_effect=blocked):
            first = scheduler._launch(fires[0].id)
            same_owner_excess = scheduler._launch(fires[1].id)
            other_owner = scheduler._launch(fires[2].id)
            self.assertIsNotNone(first)
            self.assertIsNone(same_owner_excess)
            self.assertIsNotNone(other_owner)
            self.assertEqual("queued", db.get_automation_fire(fires[1].id).status)
            blocker.set()
            await asyncio.gather(first, other_owner)

        calls: list[tuple[str, int]] = []
        identities = [("owner-a", "token-a"), ("owner-b", "token-b")]

        def pull(token: str, _device: str, *, limit: int, **_kwargs):
            calls.append((token, limit))
            return []

        with (
            patch.object(scheduler.db, "list_server_identities", return_value=identities),
            patch.object(scheduler.server_sync, "relay_device_id", return_value="device-test-0001"),
            patch.object(scheduler.server_client, "pull_relay_events", side_effect=pull),
        ):
            await scheduler._poll_relay_once()
        self.assertEqual([("token-a", 1), ("token-b", 1)], calls)


if __name__ == "__main__":
    unittest.main()
