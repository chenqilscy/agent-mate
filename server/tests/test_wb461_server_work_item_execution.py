"""WB-461 Server WorkItem to Local Agent Run contract."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import business_store  # noqa: E402
import db  # noqa: E402
import run_protocol_store  # noqa: E402
from config import settings  # noqa: E402
from routers.work_items import (  # noqa: E402
    AcceptBody,
    ExecuteBody,
    accept_item,
    execute_item,
    item_delivery,
)


class ServerWorkItemExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-461", password="password123")
        self.project = db.create_project(name="server-only", owner_id=self.owner.id)
        self.item = db.create_work_item(
            project_id=self.project.id, title="执行 Server 任务", description="生成一份结果文件",
            assignee=self.owner.id,
        )
        now = time.time()
        self.device_id = "device-owner-461"
        db.get_conn().execute(
            "INSERT INTO agent_devices "
            "(id,owner_id,name,public_key,status,created_at,updated_at,authenticated_at,last_seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (self.device_id, self.owner.id, "Local Agent", "public-key-461", "active", now, now, now, now),
        )
        db.get_conn().commit()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    def test_server_task_creates_idempotent_device_run_and_accepts_server_assets(self) -> None:
        result = execute_item(
            self.project.id, self.item["id"],
            ExecuteBody(
                target_device_id=self.device_id, local_input_key="work-item:request-461",
            ),
            self.owner, idempotency_key="request-461",
        )
        run = result["run"]
        self.assertFalse(result["duplicate"])
        self.assertEqual(self.item["id"], run["work_item_id"])
        self.assertEqual(self.project.id, run["project_id"])
        self.assertEqual(self.device_id, run["target_device_id"])
        self.assertEqual(
            ["workspace.write"], run["permission_snapshot"]["preauthorized_permissions"],
        )
        self.assertNotIn("process.execute", run["permission_snapshot"]["preauthorized_permissions"])
        self.assertEqual("doing", db.get_work_item(self.item["id"])["status"])

        replay = execute_item(
            self.project.id, self.item["id"],
            ExecuteBody(
                target_device_id=self.device_id, local_input_key="work-item:request-461",
            ),
            self.owner, idempotency_key="request-461",
        )
        self.assertTrue(replay["duplicate"])
        self.assertEqual(run["id"], replay["run"]["id"])

        delivery = item_delivery(self.project.id, self.item["id"], self.owner)
        self.assertEqual([run["id"]], [value["id"] for value in delivery["runs"]])
        self.assertEqual("queued", delivery["launches"][0]["status"])

        asset, _ = business_store.create_record(
            "business_assets", entity_type="asset", actor_id=self.owner.id,
            owner_id=self.owner.id, project_id=self.project.id,
            fields={
                "session_id": run["session_id"], "run_id": run["id"], "kind": "artifact",
                "name": "result.md", "size": 12, "sha256": "a" * 64,
                "storage_state": "committed", "object_ref": "object://sha256/test",
                "validation_status": "verified", "validation": {"sha256": "a" * 64},
            },
        )
        terminal_at = time.time()
        run_protocol_store._apply_event(
            db.get_conn(), {"run_id": run["id"]},
            {
                "type": "run.completed", "event_id": "event-terminal-461",
                "lease_epoch": 1, "occurred_at": terminal_at, "payload": {},
            }, terminal_at,
        )
        db.get_conn().commit()
        self.assertEqual("review", db.get_work_item(self.item["id"])["status"])

        accepted = accept_item(
            self.project.id, self.item["id"],
            AcceptBody(run_id=run["id"], artifact_count=1), self.owner,
        )
        self.assertEqual("done", accepted["status"])
        committed = business_store.get_record("business_assets", asset["id"])
        self.assertEqual("accepted", committed["acceptance_status"])

    def test_execute_rejects_an_oversized_idempotency_key(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            execute_item(
                self.project.id, self.item["id"],
                ExecuteBody(
                    target_device_id=self.device_id, local_input_key="work-item:request-461",
                ),
                self.owner, idempotency_key="x" * 121,
            )
        self.assertEqual(400, caught.exception.status_code)
        self.assertEqual([], business_store.list_scoped(
            "business_runs", account_id=self.owner.id, project_id=self.project.id,
            parent=("work_item_id", self.item["id"]), limit=10,
        )[0])

    def test_execute_claims_an_unassigned_work_item_once(self) -> None:
        item = db.create_work_item(
            project_id=self.project.id, title="未分配任务", assignee="",
        )
        result = execute_item(
            self.project.id, item["id"],
            ExecuteBody(
                target_device_id=self.device_id, local_input_key="work-item:claim-496",
            ),
            self.owner, idempotency_key="claim-496",
        )
        self.assertFalse(result["duplicate"])
        claimed = db.get_work_item(item["id"])
        self.assertEqual("doing", claimed["status"])
        self.assertEqual(self.owner.id, claimed["assignee"])
        activity = db.list_work_item_activity(self.project.id, item["id"])
        assignments = [value for value in activity if value["kind"] == "assignee"]
        self.assertEqual(1, len(assignments))
        self.assertEqual("未指派→owner-461", assignments[0]["detail"])

        replay = execute_item(
            self.project.id, item["id"],
            ExecuteBody(
                target_device_id=self.device_id, local_input_key="work-item:claim-496",
            ),
            self.owner, idempotency_key="claim-496",
        )
        self.assertTrue(replay["duplicate"])
        self.assertEqual(result["run"]["id"], replay["run"]["id"])
        activity = db.list_work_item_activity(self.project.id, item["id"])
        self.assertEqual(1, len([value for value in activity if value["kind"] == "assignee"]))


if __name__ == "__main__":
    unittest.main()
