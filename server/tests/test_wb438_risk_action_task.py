"""WB-438 risk Markdown/action-task/closure contract."""
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
from routers.governance import (  # noqa: E402
    ActionTaskBody,
    CreateBody,
    UpdateBody,
    create_action_task,
    create_record,
    update_record,
)
from routers.work_items import AcceptBody, UpdateBody as WorkItemUpdateBody, accept_item, update_item  # noqa: E402


class RiskActionTaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.project = db.create_project(name="governed", owner_id=self.owner.id)
        self.milestone = db.create_milestone(
            project_id=self.project.id, name="M1", due_date="2026-08-31",
        )

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_create_action_task_is_idempotent_and_risk_closure_is_evidence_gated(self) -> None:
        description = "## 触发条件\n\n支付超时后发生重试。\n\n## 关闭条件\n\n- [ ] 幂等回归通过"
        risk = create_record(self.project.id, CreateBody(
            record_type="risk", title="支付重试可能重复扣款", description=description,
            severity="critical", owner_id=self.owner.id, response="补齐幂等回归",
            milestone_id=self.milestone["id"],
        ), self.owner)
        created = create_action_task(self.project.id, risk["id"], ActionTaskBody(
            title="[风险处置] 验证支付重试幂等性", due_date="2026-08-20",
            acceptance_criteria="- [ ] 并发重试只产生一个有效结果",
        ), self.owner)
        self.assertTrue(created["created"])
        item = created["work_item"]
        self.assertEqual("urgent", item["priority"])
        self.assertEqual(self.owner.id, item["assignee"])
        self.assertEqual(self.milestone["id"], item["milestone_id"])
        self.assertEqual(["风险处置"], item["labels"])
        self.assertIn(description, item["description"])
        self.assertEqual([], created["work_item"]["attachments"])
        replay = create_action_task(self.project.id, risk["id"], ActionTaskBody(
            title="不应重复创建", acceptance_criteria="- [ ] replay",
        ), self.owner)
        self.assertFalse(replay["created"])
        self.assertEqual(item["id"], replay["work_item"]["id"])
        self.assertEqual(1, len(db.list_work_items(self.project.id)))

        update_item(self.project.id, item["id"], WorkItemUpdateBody(status="doing"), self.owner)
        self.assertEqual("mitigating", db.get_project_governance(risk["id"])["status"])
        with self.assertRaisesRegex(HTTPException, "真实交付验收"):
            update_record(self.project.id, risk["id"], UpdateBody(
                status="closed", evidence_label="残余风险为低",
            ), self.owner)

        update_item(self.project.id, item["id"], WorkItemUpdateBody(status="review"), self.owner)
        accepted = accept_item(self.project.id, item["id"], AcceptBody(
            run_id="run-verified", artifact_count=2,
        ), self.owner)
        self.assertTrue(accepted["delivery_accepted"])
        closed = update_record(self.project.id, risk["id"], UpdateBody(
            status="closed", evidence_label="回归通过；残余风险为低，由现有监控覆盖。",
        ), self.owner)
        self.assertEqual("closed", closed["status"])
        self.assertEqual("run-verified", closed["run_id"])
        self.assertGreater(closed["resolved_at"], 0)


if __name__ == "__main__":
    unittest.main()
