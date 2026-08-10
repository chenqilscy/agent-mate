"""WB-480 bounded Server Run pool, resource locks, and shutdown convergence."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import local_agent_store
from agent import run_resources, server_run_worker
from config import settings


class ServerRunParallelismTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.old_url = settings.AGENTMATE_SERVER_URL
        self.old_global = settings.SERVER_RUN_MAX_CONCURRENCY
        self.old_owner = settings.SERVER_RUN_PER_OWNER_CONCURRENCY
        settings.AGENTMATE_SERVER_URL = "http://server.test"
        server_run_worker._is_leader = True
        with server_run_worker._active_guard:
            server_run_worker._active_runs.clear()
            server_run_worker._capacity_by_owner.clear()
            server_run_worker._capacity_used = 0

    async def asyncTearDown(self) -> None:
        settings.AGENTMATE_SERVER_URL = self.old_url
        settings.SERVER_RUN_MAX_CONCURRENCY = self.old_global
        settings.SERVER_RUN_PER_OWNER_CONCURRENCY = self.old_owner
        server_run_worker._is_leader = False
        with server_run_worker._active_guard:
            server_run_worker._active_runs.clear()
            server_run_worker._capacity_by_owner.clear()
            server_run_worker._capacity_used = 0

    async def test_pool_overlaps_two_runs_and_does_not_claim_a_third_until_a_slot_opens(self) -> None:
        settings.SERVER_RUN_MAX_CONCURRENCY = 2
        settings.SERVER_RUN_PER_OWNER_CONCURRENCY = 2
        pending = [
            {"id": "run-a", "project_id": "project-a", "workspace": "project:project-a"},
            {"id": "run-b", "project_id": "project-b", "workspace": "project:project-b"},
            {"id": "run-c", "project_id": "project-c", "workspace": "project:project-c"},
        ]
        entered: list[str] = []
        running = 0
        maximum = 0
        first_pair = asyncio.Event()
        release = asyncio.Event()
        third_started = asyncio.Event()

        def claim(*_args, **_kwargs):
            return pending.pop(0) if pending else None

        async def execute(_owner, _user_token, _device_token, run):
            nonlocal running, maximum
            entered.append(run["id"])
            running += 1
            maximum = max(maximum, running)
            if running == 2:
                first_pair.set()
            if run["id"] == "run-c":
                third_started.set()
            try:
                await release.wait()
            finally:
                running -= 1

        with (
            patch.object(server_run_worker.db, "init_db"),
            patch.object(server_run_worker.local_agent_store, "acquire_run_worker_leader", return_value=True),
            patch.object(server_run_worker.local_agent_store, "publish_run_worker_snapshot", return_value=True),
            patch.object(server_run_worker.local_agent_store, "release_run_worker_leader"),
            patch.object(server_run_worker.local_agent_store, "list_server_identities", return_value=[("owner-a", "user-token")]),
            patch.object(server_run_worker.run_transport, "ensure_device", return_value="device-token"),
            patch.object(server_run_worker.run_transport, "heartbeat", return_value=True),
            patch.object(server_run_worker.run_transport, "claim_run", side_effect=claim),
            patch.object(server_run_worker, "_flush", new=AsyncMock(return_value={"acknowledged": 0, "pending": 0})),
            patch.object(server_run_worker, "execute_run", side_effect=execute),
        ):
            supervisor = asyncio.create_task(server_run_worker.run_forever())
            await asyncio.wait_for(first_pair.wait(), 2)
            await asyncio.sleep(0.6)
            self.assertEqual(["run-a", "run-b"], entered)
            self.assertEqual(2, maximum)
            release.set()
            await asyncio.wait_for(third_started.wait(), 2)
            supervisor.cancel()
            await asyncio.gather(supervisor, return_exceptions=True)

        self.assertEqual(["run-a", "run-b", "run-c"], entered)
        self.assertLessEqual(maximum, 2)

    async def test_limit_one_is_serial_and_supervisor_cancels_its_child(self) -> None:
        settings.SERVER_RUN_MAX_CONCURRENCY = 1
        settings.SERVER_RUN_PER_OWNER_CONCURRENCY = 1
        claims = [{"id": "run-one", "project_id": "", "workspace": "default"}, {"id": "run-two"}]
        entered = asyncio.Event()
        child_cancelled = asyncio.Event()

        def claim(*_args, **_kwargs):
            return claims.pop(0) if claims else None

        async def execute(*_args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                child_cancelled.set()

        with (
            patch.object(server_run_worker.db, "init_db"),
            patch.object(server_run_worker.local_agent_store, "acquire_run_worker_leader", return_value=True),
            patch.object(server_run_worker.local_agent_store, "publish_run_worker_snapshot", return_value=True),
            patch.object(server_run_worker.local_agent_store, "release_run_worker_leader"),
            patch.object(server_run_worker.local_agent_store, "list_server_identities", return_value=[("owner-a", "user-token")]),
            patch.object(server_run_worker.run_transport, "ensure_device", return_value="device-token"),
            patch.object(server_run_worker.run_transport, "heartbeat", return_value=True),
            patch.object(server_run_worker.run_transport, "claim_run", side_effect=claim) as claim_mock,
            patch.object(server_run_worker, "_flush", new=AsyncMock(return_value={"acknowledged": 0, "pending": 0})),
            patch.object(server_run_worker, "execute_run", side_effect=execute),
        ):
            supervisor = asyncio.create_task(server_run_worker.run_forever())
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.sleep(0.7)
            self.assertEqual(1, claim_mock.call_count)
            supervisor.cancel()
            await asyncio.gather(supervisor, return_exceptions=True)
            await asyncio.wait_for(child_cancelled.wait(), 1)

    async def test_workspace_writes_and_global_host_tools_are_serialized(self) -> None:
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()
        other_workspace_entered = asyncio.Event()

        async def first():
            with run_resources.bind(run_id="run-a", owner_id="owner", workspace_key="project-a"):
                async with run_resources.acquire(("workspace.write",)):
                    first_entered.set()
                    await release_first.wait()

        async def second():
            await first_entered.wait()
            with run_resources.bind(run_id="run-b", owner_id="owner", workspace_key="project-a"):
                async with run_resources.acquire(("workspace.write",)):
                    second_entered.set()

        async def other_workspace():
            await first_entered.wait()
            with run_resources.bind(run_id="run-c", owner_id="owner", workspace_key="project-c"):
                async with run_resources.acquire(("workspace.write",)):
                    other_workspace_entered.set()

        tasks = [asyncio.create_task(first()), asyncio.create_task(second()), asyncio.create_task(other_workspace())]
        await asyncio.wait_for(first_entered.wait(), 1)
        await asyncio.wait_for(other_workspace_entered.wait(), 1)
        await asyncio.sleep(0.05)
        self.assertFalse(second_entered.is_set())
        waiting = run_resources.snapshot()["waiting"]
        self.assertEqual("run-b", waiting[0]["run_id"])
        release_first.set()
        await asyncio.wait_for(second_entered.wait(), 1)
        await asyncio.gather(*tasks)

    async def test_waiting_run_releases_and_reacquires_its_compute_slot(self) -> None:
        settings.SERVER_RUN_MAX_CONCURRENCY = 1
        settings.SERVER_RUN_PER_OWNER_CONCURRENCY = 1
        self.assertTrue(server_run_worker._reserve_capacity("owner"))
        task = asyncio.create_task(asyncio.sleep(60))
        active = server_run_worker._ActiveRun(
            task=task, run_id="run-waiting", owner_id="owner", device_id="device",
            project_id="project", workspace="project:project",
        )
        with server_run_worker._active_guard:
            server_run_worker._active_runs[active.run_id] = active
        server_run_worker._set_phase(active.run_id, "waiting_user")
        server_run_worker._release_run_slot(active.run_id)
        waiting = server_run_worker.snapshot("owner")
        self.assertEqual(0, waiting["active"])
        self.assertEqual(1, waiting["resident"])
        self.assertTrue(server_run_worker._try_reacquire_run_slot(active.run_id))
        self.assertEqual(1, server_run_worker.snapshot("owner")["active"])
        server_run_worker._release_run_slot(active.run_id)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class ServerRunLeaderLeaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.LOCAL_AGENT_DB_PATH
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "local-agent.db"
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()

    def tearDown(self) -> None:
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        settings.LOCAL_AGENT_DB_PATH = self.old_path
        self.temp.cleanup()

    def test_only_one_process_claims_and_expired_leader_can_fail_over(self) -> None:
        self.assertTrue(local_agent_store.acquire_run_worker_leader("worker-a", ttl_seconds=30))
        self.assertFalse(local_agent_store.acquire_run_worker_leader("worker-b", ttl_seconds=30))
        self.assertTrue(local_agent_store.publish_run_worker_snapshot(
            "worker-a", {"active": 1, "runs": [{"run_id": "run-a"}]},
        ))
        shared = local_agent_store.read_run_worker_snapshot()
        self.assertTrue(shared["leader_active"])
        self.assertEqual("run-a", shared["snapshot"]["runs"][0]["run_id"])

        with sqlite3.connect(settings.LOCAL_AGENT_DB_PATH) as conn:
            conn.execute("UPDATE run_worker_leader SET expires_at=0 WHERE singleton=1")
            conn.commit()
        self.assertTrue(local_agent_store.acquire_run_worker_leader("worker-b", ttl_seconds=30))
        self.assertFalse(local_agent_store.publish_run_worker_snapshot("worker-a", {"active": 99}))
        failed_over = local_agent_store.read_run_worker_snapshot()
        self.assertEqual("worker-b", failed_over["holder_id"])
        self.assertEqual({}, failed_over["snapshot"])


if __name__ == "__main__":
    unittest.main()
