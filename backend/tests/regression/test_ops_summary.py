"""Execution monitoring aggregation and owner/project scope coverage (WB-286)."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
import unittest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import ops as ops_router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class OpsSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "ops.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        set_current_user_id(LOCAL_USER_ID)

    def tearDown(self) -> None:
        set_current_user_id(None)
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _completed_run(self, owner_id: str, project_id: str | None, title: str):
        session = db.create_session(owner_id=owner_id, title=title, project_id=project_id)
        run, _ = db.create_run(
            session_id=session.id, owner_id=owner_id, project_id=project_id,
            mode="exec", workspace="default",
        )
        db.update_run_runtime(run.id, prompt_tokens=10, completion_tokens=5, tool_calls=2)
        return db.set_run_status(run.id, "completed")

    def _attention_session(self, owner_id: str, project_id: str | None, title: str, status: str):
        session = db.create_session(owner_id=owner_id, title=title, project_id=project_id)
        db.get_conn().execute("UPDATE sessions SET status=? WHERE id=?", (status, session.id))
        db.get_conn().commit()
        return session

    def test_summary_uses_authoritative_manifests_and_access_scope(self) -> None:
        own = self._completed_run(LOCAL_USER_ID, None, "own delivery")
        path = settings.WORKSPACE_ROOT / "default" / "report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("verified", encoding="utf-8")
        db.upsert_artifact(run_id=own.id, path="report.md", full_path=path, source_tool="write_file")

        other = db.create_user(name="ops-other", password="pw")
        private_session = db.create_session(owner_id=other.id, title="private failure")
        private_run, _ = db.create_run(
            session_id=private_session.id, owner_id=other.id, project_id=None,
            mode="exec", workspace="default",
        )
        db.set_run_status(private_run.id, "failed", error_message="private")
        self._attention_session(LOCAL_USER_ID, None, "legacy local running", "running")
        self._attention_session(other.id, None, "hidden private running", "running")

        shared = db.create_project(owner_id=other.id, name="shared ops")
        db.add_project_member(shared.id, LOCAL_USER_ID, Role.MEMBER)
        self._completed_run(other.id, shared.id, "shared delivery")
        self._attention_session(other.id, shared.id, "shared waiting", "waiting")
        db.create_work_item(
            project_id=shared.id, owner_id=other.id, title="overdue",
            status="doing", due_date="2000-01-01",
        )
        assistant = db.create_assistant(owner_id=LOCAL_USER_ID, name="ops assistant")
        db.create_channel(assistant_id=assistant["id"], type="telegram", enabled=True)
        db.create_assistant(owner_id=other.id, name="hidden assistant")

        now = time.time()
        auto = db.create_automation(owner_id=LOCAL_USER_ID, name="ops auto", prompt="run")
        db.get_conn().execute(
            """INSERT INTO automation_fires
               (id,automation_id,owner_id,fire_key,trigger_kind,planned_at,status,attempt,max_attempts,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,1,3,?,?)""",
            ("ops-fire", auto.id, LOCAL_USER_ID, "ops-key", "manual", now, "dead_letter", now, now),
        )
        db.get_conn().commit()

        summary = ops_router.ops_summary(7)
        self.assertEqual(2, summary["runs"]["total"])
        self.assertEqual(2, summary["runs"]["succeeded"])
        self.assertEqual(0, summary["runs"]["failed"])
        self.assertEqual(2, summary["runs"]["attention_sessions"])
        self.assertEqual(100.0, summary["runs"]["success_rate"])
        self.assertEqual(1, summary["artifacts"]["pending_review"])
        self.assertEqual("report.md", summary["recent_artifacts"][0]["path"])
        self.assertEqual(1, summary["projects"]["overdue"])
        self.assertEqual(1, summary["automations"]["dead_letter"])
        self.assertEqual(1, summary["assistants"]["total"])
        self.assertEqual(1, summary["assistants"]["channels_attention"])


if __name__ == "__main__":
    unittest.main()
