"""WB-496 cross-project action ordering and execute authorization boundaries."""
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

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.work_items import ExecuteBody, execute_item, personal_action_items  # noqa: E402


class PersonalActionBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.account = db.create_account(name="account-496", password="password123")
        self.peer = db.create_account(name="peer-496", password="password123")
        self.viewer = db.create_account(name="viewer-496", password="password123")
        self.outsider = db.create_account(name="outsider-496", password="password123")
        self.first = db.create_project(name="Alpha", owner_id=self.account.id)
        self.second = db.create_project(name="Beta", owner_id=self.peer.id)
        self.private = db.create_project(name="Private", owner_id=self.outsider.id)
        db.add_project_member(self.second.id, self.account.id, Role.MEMBER)
        db.add_project_member(self.first.id, self.viewer.id, Role.VIEWER)
        now = time.time()
        self.device_id = "device-account-496"
        db.get_conn().execute(
            "INSERT INTO agent_devices "
            "(id,owner_id,name,public_key,status,created_at,updated_at,authenticated_at,last_seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (self.device_id, self.account.id, "Local Agent", "public-key", "active", now, now, now, now),
        )
        db.get_conn().commit()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_two_authorized_projects_sort_same_reason_by_priority_and_date_boundary(self) -> None:
        high = db.create_work_item(
            project_id=self.first.id, title="High", assignee=self.account.id,
            priority="high", due_date="2026-08-10",
        )
        urgent = db.create_work_item(
            project_id=self.second.id, title="Urgent", assignee=self.account.id,
            priority="urgent", due_date="2026-08-10",
        )
        tomorrow = db.create_work_item(
            project_id=self.second.id, title="Tomorrow", assignee=self.account.id,
            priority="high", due_date="2026-08-11",
        )
        db.create_work_item(
            project_id=self.private.id, title="Invisible", assignee=self.account.id,
            priority="urgent", due_date="2026-08-09",
        )

        on_tenth = personal_action_items("2026-08-10", self.account)
        self.assertEqual([urgent["id"], high["id"]], [item["id"] for item in on_tenth["items"]])
        self.assertEqual({self.first.id, self.second.id}, {
            item["project"]["id"] for item in on_tenth["items"]
        })
        self.assertNotIn("Invisible", {item["title"] for item in on_tenth["items"]})
        self.assertEqual(1, on_tenth["summary"]["backlog"])

        on_eleventh = personal_action_items("2026-08-11", self.account)
        tomorrow_item = next(item for item in on_eleventh["items"] if item["id"] == tomorrow["id"])
        self.assertEqual("due_today", tomorrow_item["action_reason"])

    def test_viewer_can_read_but_cannot_execute_and_done_or_missing_device_fail_closed(self) -> None:
        viewer_item = db.create_work_item(
            project_id=self.first.id, title="Viewer task", assignee=self.viewer.id,
            due_date="2026-08-10",
        )
        visible = personal_action_items("2026-08-10", self.viewer)
        self.assertEqual([viewer_item["id"]], [item["id"] for item in visible["items"]])
        self.assertEqual(Role.VIEWER.value, visible["items"][0]["project"]["role"])

        with self.assertRaises(HTTPException) as viewer_error:
            execute_item(
                self.first.id, viewer_item["id"],
                ExecuteBody(target_device_id=self.device_id, local_input_key="viewer-run-496"),
                self.viewer, idempotency_key="viewer-run-496",
            )
        self.assertEqual(403, viewer_error.exception.status_code)

        completed = db.create_work_item(
            project_id=self.first.id, title="Done", assignee=self.account.id, status="done",
        )
        with self.assertRaises(HTTPException) as completed_error:
            execute_item(
                self.first.id, completed["id"],
                ExecuteBody(target_device_id=self.device_id, local_input_key="done-run-496"),
                self.account, idempotency_key="done-run-496",
            )
        self.assertEqual(409, completed_error.exception.status_code)

        pending = db.create_work_item(
            project_id=self.first.id, title="No device", assignee=self.account.id,
        )
        with self.assertRaises(HTTPException) as device_error:
            execute_item(
                self.first.id, pending["id"],
                ExecuteBody(target_device_id="missing-device-496", local_input_key="nodevice-run-496"),
                self.account, idempotency_key="nodevice-run-496",
            )
        self.assertEqual(400, device_error.exception.status_code)


if __name__ == "__main__":
    unittest.main()
