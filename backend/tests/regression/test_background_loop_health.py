"""Recurring worker health and recovery visibility (WB-359)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, PropertyMock

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import background_worker, scheduler, worker_health  # noqa: E402
from config import settings  # noqa: E402


class BackgroundLoopHealthTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        worker_health.reset_for_tests()

    async def test_scheduler_failure_is_logged_and_next_success_recovers(self) -> None:
        with (
            patch.object(type(settings), "server_enabled", new_callable=PropertyMock, return_value=False),
            patch.object(scheduler, "_scan_once", AsyncMock(side_effect=OSError("db offline"))),
            self.assertLogs("agentmate.scheduler", level="ERROR") as captured,
        ):
            await scheduler._tick()
        failed = worker_health.snapshot()
        component = failed["components"][0]
        self.assertFalse(failed["healthy"])
        self.assertEqual(1, component["consecutive_failures"])
        self.assertIn("OSError: db offline", component["last_error"])
        self.assertTrue(any("automation_scheduler.scan" in line for line in captured.output))

        with (
            patch.object(type(settings), "server_enabled", new_callable=PropertyMock, return_value=False),
            patch.object(scheduler, "_scan_once", AsyncMock()),
        ):
            await scheduler._tick()
        recovered = worker_health.snapshot()["components"][0]
        self.assertEqual(0, recovered["consecutive_failures"])
        self.assertIsNone(recovered["last_error"])
        self.assertIsNotNone(recovered["last_success_at"])

    async def test_server_outbox_and_durable_worker_are_independently_visible(self) -> None:
        with (
            patch.object(type(settings), "server_enabled", new_callable=PropertyMock, return_value=True),
            patch.object(scheduler, "_scan_once", AsyncMock()),
            patch.object(scheduler.server_sync, "flush_outbox", side_effect=RuntimeError("server down")),
            self.assertLogs("agentmate.scheduler", level="ERROR"),
        ):
            await scheduler._tick()
        by_name = {item["name"]: item for item in worker_health.snapshot()["components"]}
        self.assertEqual(0, by_name["automation_scheduler.scan"]["consecutive_failures"])
        self.assertEqual(1, by_name["server_sync.outbox"]["consecutive_failures"])

        with (
            patch.object(background_worker, "scan_once", AsyncMock(side_effect=ValueError("bad lease"))),
            self.assertLogs("agentmate.background_worker", level="ERROR"),
        ):
            await background_worker._scan_tick()
        by_name = {item["name"]: item for item in worker_health.snapshot()["components"]}
        self.assertEqual(1, by_name["background_worker.scan"]["consecutive_failures"])


if __name__ == "__main__":
    unittest.main()
