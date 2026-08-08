"""WB-400: backend resources use one auditable lifespan with rollback cleanup."""
from __future__ import annotations

import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import main  # noqa: E402


class BackendLifespanTest(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_starts_and_stops_resources_in_reverse_order(self) -> None:
        order: list[str] = []

        def async_mark(name: str):
            async def mark() -> None:
                order.append(name)
            return mark

        with (
            patch.object(main.settings, "AGENTMATE_SERVER_URL", ""),
            patch.object(main, "_startup", side_effect=lambda: order.append("db")),
            patch.object(main.scheduler, "start", side_effect=lambda: order.append("scheduler.start")),
            patch.object(main.scheduler, "stop", new=async_mark("scheduler.stop")),
            patch.object(main.background_worker, "start", new=async_mark("worker.start")),
            patch.object(main.background_worker, "stop", new=async_mark("worker.stop")),
            patch.object(main.channel_manager, "refresh", new=async_mark("channels.start")),
            patch.object(main.channel_manager, "stop", new=async_mark("channels.stop")),
            patch.object(main.telemetry, "shutdown", side_effect=lambda: order.append("telemetry.stop")),
            patch.object(main.server_client, "close", side_effect=lambda: order.append("client.stop")),
        ):
            async with main._lifespan(main.app):
                order.append("serving")

        self.assertEqual([
            "db", "scheduler.start", "worker.start", "channels.start", "serving",
            "channels.stop", "worker.stop", "scheduler.stop", "telemetry.stop", "client.stop",
        ], order)

    async def test_partial_startup_failure_still_cleans_started_resources(self) -> None:
        with (
            patch.object(main.settings, "AGENTMATE_SERVER_URL", ""),
            patch.object(main, "_startup"),
            patch.object(main.scheduler, "start"),
            patch.object(main.scheduler, "stop", new_callable=AsyncMock) as stop_scheduler,
            patch.object(main.background_worker, "start", new_callable=AsyncMock, side_effect=RuntimeError("db locked")),
            patch.object(main.background_worker, "stop", new_callable=AsyncMock) as stop_worker,
            patch.object(main.channel_manager, "stop", new_callable=AsyncMock) as stop_channels,
            patch.object(main.telemetry, "shutdown") as stop_telemetry,
            patch.object(main.server_client, "close") as close_client,
            self.assertRaisesRegex(RuntimeError, "db locked"),
        ):
            async with main._lifespan(main.app):
                self.fail("startup failure must not yield")

        stop_channels.assert_not_awaited()
        stop_worker.assert_awaited_once()
        stop_scheduler.assert_awaited_once()
        stop_telemetry.assert_called_once_with()
        close_client.assert_called_once_with()

    async def test_database_startup_failure_still_closes_process_clients(self) -> None:
        with (
            patch.object(main.settings, "AGENTMATE_SERVER_URL", ""),
            patch.object(main, "_startup", side_effect=RuntimeError("migration failed")),
            patch.object(main.scheduler, "start") as start_scheduler,
            patch.object(main.telemetry, "shutdown") as stop_telemetry,
            patch.object(main.server_client, "close") as close_client,
            self.assertRaisesRegex(RuntimeError, "migration failed"),
        ):
            async with main._lifespan(main.app):
                self.fail("database startup failure must not yield")

        start_scheduler.assert_not_called()
        stop_telemetry.assert_called_once_with()
        close_client.assert_called_once_with()

    async def test_server_mode_starts_and_cancels_run_worker_without_local_scheduler(self) -> None:
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def run_worker() -> None:
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        with (
            patch.object(main.settings, "AGENTMATE_SERVER_URL", "https://server.example.test"),
            patch.object(main, "_startup"),
            patch.object(main.server_run_worker, "run_forever", side_effect=run_worker),
            patch.object(main.scheduler, "start") as start_scheduler,
            patch.object(main.background_worker, "start", new_callable=AsyncMock),
            patch.object(main.background_worker, "stop", new_callable=AsyncMock),
            patch.object(main.channel_manager, "refresh", new_callable=AsyncMock),
            patch.object(main.channel_manager, "stop", new_callable=AsyncMock),
            patch.object(main.telemetry, "shutdown"),
            patch.object(main.server_client, "close"),
        ):
            async with main._lifespan(main.app):
                await asyncio.wait_for(started.wait(), timeout=1)
                start_scheduler.assert_not_called()

        self.assertTrue(stopped.is_set())

    def test_deprecated_event_registries_are_empty(self) -> None:
        self.assertEqual([], main.app.router.on_startup)
        self.assertEqual([], main.app.router.on_shutdown)


if __name__ == "__main__":
    unittest.main()
