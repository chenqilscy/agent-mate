"""WB-350 shared risk/decision governance contract."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.governance import CreateBody, UpdateBody, create_record, delete_record, list_activity, list_records, update_record  # noqa: E402


class ProjectGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.member = db.create_account(name="member", password="password123")
        self.viewer = db.create_account(name="viewer", password="password123")
        self.outsider = db.create_account(name="outsider", password="password123")
        self.project = db.create_project(name="governed", owner_id=self.owner.id)
        self.other = db.create_project(name="other", owner_id=self.outsider.id)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)
        self.work = db.create_work_item(project_id=self.project.id, title="release", assignee="")
        self.milestone = db.create_milestone(project_id=self.project.id, name="M1")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None: conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_risk_decision_lifecycle_refs_and_audit(self) -> None:
        risk = create_record(self.project.id, CreateBody(
            record_type="risk", title="上线延期", severity="high", owner_id=self.member.id,
            response="拆分交付", work_item_id=self.work["id"], milestone_id=self.milestone["id"],
            run_id="local-run", artifact_id="local-artifact", evidence_label="App 验证",
        ), self.member)
        self.assertEqual("open", risk["status"])
        self.assertEqual("member", risk["owner_name"])
        closed = update_record(self.project.id, risk["id"], UpdateBody(status="closed"), self.owner)
        self.assertGreater(closed["resolved_at"], 0)
        decision = create_record(self.project.id, CreateBody(
            record_type="decision", title="采用灰度发布", rationale="降低变更风险",
        ), self.owner)
        accepted = update_record(self.project.id, decision["id"], UpdateBody(status="accepted"), self.owner)
        self.assertEqual("accepted", accepted["status"])
        self.assertEqual(2, len(list_records(self.project.id, self.viewer)["records"]))
        self.assertEqual(4, len(list_activity(self.project.id, self.viewer)["activity"]))
        delete_record(self.project.id, decision["id"], self.owner)
        self.assertEqual("deleted", list_activity(self.project.id, self.owner)["activity"][0]["kind"])

    def test_roles_ref_ownership_and_delete_cleanup(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Viewer is read-only"):
            create_record(self.project.id, CreateBody(record_type="risk", title="no", severity="low"), self.viewer)
        with self.assertRaisesRegex(HTTPException, "existing project member"):
            create_record(self.project.id, CreateBody(
                record_type="risk", title="bad owner", severity="low", owner_id=self.outsider.id,
            ), self.owner)
        other_work = db.create_work_item(project_id=self.other.id, title="other", assignee="")
        with self.assertRaisesRegex(HTTPException, "work item must belong"):
            create_record(self.project.id, CreateBody(
                record_type="risk", title="cross", severity="low", work_item_id=other_work["id"],
            ), self.owner)
        record = create_record(self.project.id, CreateBody(
            record_type="risk", title="cleanup", severity="medium",
            work_item_id=self.work["id"], milestone_id=self.milestone["id"],
        ), self.owner)
        db.delete_work_item(self.work["id"]); db.delete_milestone(self.milestone["id"])
        cleaned = db.get_project_governance(record["id"])
        self.assertEqual("", cleaned["work_item_id"]); self.assertEqual("", cleaned["milestone_id"])

    def test_activity_order_uses_sequence_when_timestamps_match(self) -> None:
        with patch.object(db.time, "time", return_value=123456.0):
            record = create_record(self.project.id, CreateBody(
                record_type="decision", title="same timestamp",
            ), self.owner)
            update_record(self.project.id, record["id"], UpdateBody(status="accepted"), self.owner)
            delete_record(self.project.id, record["id"], self.owner)
        activity = list_activity(self.project.id, self.owner)["activity"]
        self.assertEqual(["deleted", "updated", "created"], [item["kind"] for item in activity])
        sequences = [item["sequence"] for item in activity]
        self.assertEqual(sorted(sequences, reverse=True), sequences)


if __name__ == "__main__":
    unittest.main()
