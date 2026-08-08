"""WB-461 leased Server Runs commit artifacts without an App event follower."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent import events, server_run_worker
from config import settings
from storage import db


class ServerRunArtifactCommitTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.temp.name) / "execution-cache.db"
        db._local = threading.local()
        db.init_db()

    async def asyncTearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        settings.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_artifact_is_committed_before_terminal_event(self) -> None:
        emitted: list[str] = []
        runtime_options: dict = {}

        async def fake_chat(*_args, **kwargs):
            runtime_options.update(kwargs)
            yield events.artifact("result.md", "12 B", "result.md")
            yield events.done("message-local")

        def append(_run_id: str, event_type: str, _payload=None):
            emitted.append(event_type)
            return {"event_id": f"event-{len(emitted)}"}

        run = {
            "id": "server-run-artifact-461", "session_id": "server-session-artifact-461",
            "_lease_epoch": 1, "owner_id": "owner-server-artifact-461",
            "project_id": "project-server-artifact-461", "mode": "exec",
            "workspace": "project:project-server-artifact-461", "model_ref": None,
            "request_snapshot": {"loadout": {}, "refs": []},
            "permission_snapshot": {
                "execution_source": "background",
                "preauthorized_permissions": ["workspace.write"],
            },
        }
        commit = AsyncMock()
        with (
            patch.object(server_run_worker.server_client, "verify_token", return_value={"id": run["owner_id"], "name": "Owner"}),
            patch.object(server_run_worker.server_client, "get_business_session", return_value={"id": run["session_id"], "title": "Task", "kind": "projexec"}),
            patch.object(server_run_worker.server_client, "get_business_messages", return_value=[{
                "id": "message-461", "run_id": run["id"], "role": "user", "content": "执行任务",
            }]),
            patch.object(server_run_worker.server_client, "get_project", return_value={
                "id": run["project_id"], "name": "Server Project", "role": "Owner",
                "owner_id": run["owner_id"],
            }),
            patch.object(server_run_worker.runtime, "run_chat", side_effect=fake_chat),
            patch.object(server_run_worker, "_commit_artifact", commit),
            patch.object(server_run_worker.run_transport, "append_event", side_effect=append),
            patch.object(server_run_worker.run_transport, "flush_wal", return_value={"acknowledged": 1, "pending": 0}),
            patch.object(server_run_worker.run_transport, "renew_lease", return_value={"commands": []}),
            patch.object(server_run_worker.run_transport, "lease_status", return_value="completed"),
        ):
            await server_run_worker.execute_run(
                run["owner_id"], "server-user-token", "device-token", run,
            )

        commit.assert_awaited_once()
        self.assertEqual("server-user-token", runtime_options["server_token_override"])
        self.assertEqual("background", runtime_options["execution_source"])
        self.assertEqual(["workspace.write"], runtime_options["preauthorized_permissions"])
        self.assertLess(emitted.index("ui.artifact"), emitted.index("run.completed"))


if __name__ == "__main__":
    unittest.main()
