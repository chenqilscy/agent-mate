"""WB-441 Local Agent executes leased Server Runs and emits only WAL events."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import events, server_run_worker
from config import settings
from storage import db


class ServerRunWorkerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.temp.name) / "execution-cache.db"
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        db.init_db()

    async def asyncTearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        settings.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_worker_converts_runtime_stream_to_wal_and_terminal_event(self) -> None:
        emitted: list[tuple[str, dict]] = []
        runtime_options: dict = {}

        async def fake_chat(*_args, **kwargs):
            runtime_options.update(kwargs)
            yield events.run({"id": "local-only-run"})
            yield events.status("running")
            yield events.think("分析")
            yield events.text("真实结果")
            yield events.usage(1, 7, {"prompt_tokens": 7, "completion_tokens": 3})
            yield events.done("local-only-message")

        def append(_run_id: str, event_type: str, payload=None):
            emitted.append((event_type, payload or {}))
            return {"event_id": f"event-{len(emitted)}"}

        run = {
            "id": "server-run-441", "session_id": "server-session-441",
            "_lease_epoch": 7,
            "owner_id": "owner-server-441", "project_id": None, "mode": "ask",
            "workspace": "default", "model_ref": None,
            "request_snapshot": {"loadout": {}, "refs": []},
            "permission_snapshot": {
                "execution_source": "background", "max_total_tokens": 4096,
                "preauthorized_permissions": ["read_file"],
            },
        }
        with (
            patch.object(server_run_worker.server_client, "verify_token", return_value={"id": run["owner_id"], "name": "Owner"}),
            patch.object(server_run_worker.server_client, "get_business_session", return_value={"id": run["session_id"], "title": "Task", "kind": "chat"}),
            patch.object(server_run_worker.server_client, "get_business_messages", return_value=[{
                "id": "message-441", "run_id": run["id"], "role": "user", "content": "执行",
            }]),
            patch.object(server_run_worker.runtime, "run_chat", side_effect=fake_chat),
            patch.object(server_run_worker.run_transport, "append_event", side_effect=append),
            patch.object(server_run_worker.run_transport, "flush_wal", return_value={"acknowledged": 1, "pending": 0}),
            patch.object(server_run_worker.run_transport, "renew_lease", return_value={"commands": []}),
            patch.object(server_run_worker.run_transport, "lease_status", return_value="completed"),
        ):
            await server_run_worker.execute_run(
                run["owner_id"], "server-user-token", "device-token", run,
            )

        self.assertEqual("run.started", emitted[0][0])
        self.assertNotIn("ui.run", [event_type for event_type, _ in emitted])
        self.assertIn(("ui.text", {"md": "真实结果"}), emitted)
        self.assertEqual("run.completed", emitted[-1][0])
        self.assertEqual("background", runtime_options["execution_source"])
        self.assertEqual(4096, runtime_options["max_total_tokens"])
        self.assertEqual(["read_file"], runtime_options["preauthorized_permissions"])
        self.assertEqual("server-run:server-run-441:epoch:7", runtime_options["idempotency_key"])

    async def test_preflight_failure_is_durable_instead_of_escaping_worker(self) -> None:
        emitted: list[tuple[str, dict]] = []
        run = {
            "id": "server-run-preflight", "session_id": "server-session-preflight",
            "owner_id": "owner-server-preflight", "request_snapshot": {},
        }

        def append(_run_id: str, event_type: str, payload=None):
            emitted.append((event_type, payload or {}))
            return {"event_id": f"event-{len(emitted)}"}

        with (
            patch.object(server_run_worker.server_client, "verify_token", return_value=None),
            patch.object(server_run_worker.server_client, "get_business_session", return_value=None),
            patch.object(server_run_worker.server_client, "get_business_messages", return_value=None),
            patch.object(server_run_worker.run_transport, "append_event", side_effect=append),
            patch.object(server_run_worker.run_transport, "flush_wal", return_value={"acknowledged": 2, "pending": 0}),
            patch.object(server_run_worker.run_transport, "lease_status", return_value="completed"),
        ):
            await server_run_worker.execute_run(
                run["owner_id"], "server-user-token", "device-token", run,
            )

        self.assertEqual(["ui.error", "run.failed"], [item[0] for item in emitted])
        self.assertEqual("local_agent_preflight", emitted[-1][1]["error_code"])


if __name__ == "__main__":
    unittest.main()
