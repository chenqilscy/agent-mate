"""WB-500 Console WorkItem execution projection boundaries."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import run_protocol_store  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.work_items import (  # noqa: E402
    ExecuteBody,
    _console_event,
    execute_item,
    item_delivery,
)


class ConsoleExecutionProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-500", password="password123")
        self.viewer = db.create_account(name="viewer-500", password="password123")
        self.project = db.create_project(name="projection", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)
        self.item = db.create_work_item(
            project_id=self.project.id,
            title="查看真实执行投影",
            description="生成可验收产物",
            assignee=self.owner.id,
        )
        now = time.time()
        self.device_id = "device-console-projection-500"
        self.capabilities = {
            "capabilities": ["run_events_v1", "llm.chat", "agent.tools"],
            "max_parallel_runs": 1,
        }
        db.get_conn().execute(
            "INSERT INTO agent_devices "
            "(id,owner_id,name,public_key,status,protocol_version,capabilities,created_at,updated_at,authenticated_at,last_seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.device_id,
                self.owner.id,
                "办公室 Local Agent",
                "public-key-500",
                "active",
                1,
                '{"capabilities":["run_events_v1","llm.chat","agent.tools"],"max_parallel_runs":1}',
                now,
                now,
                now,
                now,
            ),
        )
        db.get_conn().commit()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    def _event(
        self,
        run_id: str,
        epoch: int,
        sequence: int,
        event_type: str,
        payload: dict,
    ) -> dict:
        occurred_at = time.time() + sequence / 1000
        return {
            "event_id": f"event-500-{sequence}",
            "sequence": sequence,
            "type": event_type,
            "occurred_at": occurred_at,
            "payload": payload,
            "hash": run_protocol_store.event_digest(
                run_id=run_id,
                device_id=self.device_id,
                lease_epoch=epoch,
                sequence=sequence,
                event_type=event_type,
                occurred_at=occurred_at,
                payload=payload,
            ),
        }

    def test_viewer_projection_is_read_only_allowlisted_and_redacted(self) -> None:
        created = execute_item(
            self.project.id,
            self.item["id"],
            ExecuteBody(
                target_device_id=self.device_id,
                local_input_key="private-local-input-500",
            ),
            self.owner,
            idempotency_key="console-projection-500",
        )
        run_id = created["run"]["id"]

        queued = item_delivery(self.project.id, self.item["id"], self.viewer)
        self.assertFalse(queued["can_write"])
        self.assertEqual("awaiting_claim", queued["runs"][0]["queue_context"]["reason"])
        self.assertNotIn("request_snapshot", queued["runs"][0])
        self.assertNotIn("permission_snapshot", queued["runs"][0])
        self.assertNotIn("checkpoint", queued["runs"][0])

        principal = run_protocol_store.DevicePrincipal(
            device_id=self.device_id,
            owner_id=self.owner.id,
            capabilities=self.capabilities,
            protocol_version=1,
        )
        lease = run_protocol_store.lease_run(principal, lease_seconds=60)
        assert lease is not None
        epoch = lease["lease_epoch"]
        events = [
            self._event(run_id, epoch, 1, "run.started", {"source": "local_agent"}),
            self._event(
                run_id,
                epoch,
                2,
                "ui.step",
                {
                    "tool": "read_file",
                    "label": "Bearer abcdefghijklmnop 读取 C:\\Users\\owner\\secret.txt",
                },
            ),
            self._event(
                run_id,
                epoch,
                3,
                "ui.file_read",
                {"path": "C:\\Users\\owner\\secret.txt", "range": "1-2"},
            ),
        ]
        run_protocol_store.submit_events(
            principal,
            run_id=run_id,
            lease_id=lease["lease_id"],
            lease_epoch=epoch,
            events=events,
        )

        projected = item_delivery(self.project.id, self.item["id"], self.viewer)
        run = projected["runs"][0]
        self.assertEqual(
            {"id": self.device_id, "name": "办公室 Local Agent"},
            run["device"],
        )
        self.assertEqual(["run.started", "ui.step"], [event["type"] for event in run["events"]])
        label = run["events"][1]["payload"]["label"]
        self.assertIn("[本机路径]", label)
        self.assertIn("[已脱敏]", label)
        self.assertNotIn("owner", label)
        self.assertNotIn("abcdefghijklmnop", label)

    def test_run_history_is_stably_paginated(self) -> None:
        for index in range(2):
            execute_item(
                self.project.id,
                self.item["id"],
                ExecuteBody(
                    target_device_id=self.device_id,
                    local_input_key=f"private-local-input-500-{index}",
                ),
                self.owner,
                idempotency_key=f"console-pagination-500-{index}",
            )
            time.sleep(0.01)

        first = item_delivery(self.project.id, self.item["id"], self.owner, limit=1)
        self.assertEqual(1, len(first["runs"]))
        self.assertTrue(first["next_cursor"])
        second = item_delivery(
            self.project.id,
            self.item["id"],
            self.owner,
            limit=1,
            cursor=first["next_cursor"],
        )
        self.assertEqual(1, len(second["runs"]))
        self.assertNotEqual(first["runs"][0]["id"], second["runs"][0]["id"])

    def test_malformed_optional_event_fields_cannot_break_projection(self) -> None:
        waiting = _console_event({
            "type": "run.waiting_user",
            "payload": {"questions": {"unexpected": True}},
        })
        self.assertEqual([], waiting["payload"]["questions"])
        usage = _console_event({
            "type": "ui.usage",
            "sequence": "not-a-number",
            "payload": {"used": {"unexpected": True}, "detail": {"prompt_tokens": "bad"}},
        })
        self.assertEqual(0, usage["sequence"])
        self.assertEqual(0, usage["payload"]["used"])
        self.assertEqual(0, usage["payload"]["prompt_tokens"])


if __name__ == "__main__":
    unittest.main()
