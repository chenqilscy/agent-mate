"""WB-493 Server-authoritative personal action inbox coverage."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.work_items import personal_action_items  # noqa: E402


class PersonalActionItemsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-493", password="password123")
        self.member = db.create_account(name="member-493", password="password123")
        self.outsider = db.create_account(name="outsider-493", password="password123")
        self.project = db.create_project(name="共享项目", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.member.id, Role.VIEWER)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def _item(self, title: str, **values):
        return db.create_work_item(
            project_id=self.project.id, title=title,
            assignee=values.pop("assignee", self.member.id), **values,
        )

    def test_inbox_is_access_scoped_categorized_and_sorted(self) -> None:
        overdue = self._item("逾期任务", due_date="2026-08-09", priority="urgent")
        today = self._item("今日任务", due_date="2026-08-10", priority="high")
        self._item("进行中任务", status="doing")
        self._item("阻塞任务", status="paused")
        self._item("待验收任务", status="review")
        self._item("今天开始", start_date="2026-08-10")
        self._item("未来任务", due_date="2026-08-11")
        self._item("无日期待办")
        self._item("已完成", status="done", due_date="2026-08-01")
        unassigned = self._item("未分配今日任务", assignee="", due_date="2026-08-10")
        self._item("他人任务", assignee=self.owner.id, due_date="2026-08-10")

        private_project = db.create_project(name="不可见项目", owner_id=self.outsider.id)
        db.create_work_item(
            project_id=private_project.id, title="越权任务", assignee=self.member.id,
            due_date="2026-08-09",
        )

        result = personal_action_items("2026-08-10", self.member)

        ids = [item["id"] for item in result["items"]]
        self.assertEqual(overdue["id"], ids[0])
        self.assertEqual(today["id"], ids[1])
        self.assertNotIn("越权任务", {item["title"] for item in result["items"]})
        self.assertNotIn("已完成", {item["title"] for item in result["items"]})
        self.assertNotIn("他人任务", {item["title"] for item in result["items"]})
        self.assertEqual([unassigned["id"]], [item["id"] for item in result["unassigned"]])
        self.assertTrue(all(item["project"]["role"] == Role.VIEWER.value for item in result["items"]))
        self.assertEqual(2, result["summary"]["backlog"])
        self.assertEqual(1, result["summary"]["overdue"])
        self.assertEqual("server", result["source"])
        self.assertEqual("2026-08-10", result["as_of"])

    def test_invalid_date_fails_closed(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            personal_action_items("10-08-2026", self.member)
        self.assertEqual(400, caught.exception.status_code)


if __name__ == "__main__":
    unittest.main()
