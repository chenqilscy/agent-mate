"""WB-350 local-first governance mirror and write proxy regression."""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import governance  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class ProjectGovernanceRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH; self.old_url = settings.AGENTMATE_SERVER_URL
        self._close(); settings.DB_PATH = Path(self.tmp.name) / "app.db"; settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        db.init_db(); set_current_user_id(LOCAL_USER_ID)
        self.local = db.create_project(owner_id=LOCAL_USER_ID, name="local")
        self.work = db.create_work_item(project_id=self.local.id, owner_id=LOCAL_USER_ID, title="task")
        self.milestone = db.create_milestone(project_id=self.local.id, name="M1")
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="run", kind="projexec", project_id=self.local.id)
        self.run, _ = db.create_run(session_id=self.session.id, owner_id=LOCAL_USER_ID,
                                    project_id=self.local.id, mode="exec", workspace=f"projects/{self.local.id}")

    def tearDown(self) -> None:
        set_current_user_id(None); self._close(); settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url; self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None: conn.close(); db._local.conn = None

    def test_local_crud_validates_refs_and_cleans_dangling_links(self) -> None:
        created = governance.create_record(governance.CreateBody(
            project_id=self.local.id, record_type="risk", title="delivery", severity="high",
            owner_id=LOCAL_USER_ID, work_item_id=self.work.id, milestone_id=self.milestone["id"],
            run_id=self.run.id, response="rollback",
        ), authorization="")
        self.assertEqual("open", created["status"])
        updated = governance.update_record(created["id"], governance.UpdateBody(status="closed"), authorization="")
        self.assertGreater(updated["resolved_at"], 0)
        other = db.create_project(owner_id=LOCAL_USER_ID, name="other")
        other_work = db.create_work_item(project_id=other.id, owner_id=LOCAL_USER_ID, title="other")
        with self.assertRaisesRegex(HTTPException, "work item must belong"):
            governance.update_record(created["id"], governance.UpdateBody(work_item_id=other_work.id), authorization="")
        db.delete_work_item(self.work.id); db.delete_milestone(self.milestone["id"]); db.delete_session(self.session.id)
        cleaned = db.get_project_governance(created["id"])
        self.assertEqual("", cleaned["work_item_id"]); self.assertEqual("", cleaned["milestone_id"]); self.assertEqual("", cleaned["run_id"])

    def test_viewer_is_read_only_and_server_write_fails_closed(self) -> None:
        viewer = db.create_user(name="viewer", password="pw", role=Role.VIEWER)
        db.add_project_member(self.local.id, viewer.id, Role.VIEWER); set_current_user_id(viewer.id)
        with self.assertRaises(HTTPException) as denied:
            governance.create_record(governance.CreateBody(project_id=self.local.id, record_type="decision", title="no"), authorization="")
        self.assertEqual(403, denied.exception.status_code)

        set_current_user_id(LOCAL_USER_ID)
        db.mirror_server_project(id="server-project", name="shared", owner_id=LOCAL_USER_ID,
                                 instruction="", created_at=1, updated_at=1)
        db.mirror_server_project_governance("server-project", [{
            "id": "risk-1", "project_id": "server-project", "record_type": "risk", "title": "remote",
            "description": "", "status": "open", "severity": "medium", "owner_id": LOCAL_USER_ID,
            "response": "", "rationale": "", "work_item_id": "", "milestone_id": "", "run_id": "",
            "artifact_id": "", "evidence_label": "", "created_by": LOCAL_USER_ID,
            "created_at": 1, "updated_at": 2, "resolved_at": 0,
        }])
        with patch.object(governance.server_client, "update_project_governance", return_value=None):
            with self.assertRaises(HTTPException) as failed:
                governance.update_record("risk-1", governance.UpdateBody(title="must-not-stick"), authorization="Bearer token")
        self.assertEqual(503, failed.exception.status_code)
        self.assertEqual("remote", db.get_project_governance("risk-1")["title"])


if __name__ == "__main__":
    unittest.main()
