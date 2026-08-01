"""WorkItem → Run → Artifact → acceptance collaboration coverage (WB-255)."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import work_item_runner  # noqa: E402
import server_sync  # noqa: E402
from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import work_items as work_items_router  # noqa: E402
from storage import background_job_store as job_store, db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class WorkItemDeliveryCollaborationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        job_store.ensure_tables()
        self.project = db.create_project(owner_id=LOCAL_USER_ID, name="delivery")
        self.item = db.create_work_item(
            project_id=self.project.id, owner_id=LOCAL_USER_ID,
            title="交付报告", description="生成报告文件",
        )
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

    async def test_member_launch_is_idempotent_and_acceptance_closes_full_chain(self) -> None:
        async def completed_run(session, user, _prompt, **kwargs):
            ref = kwargs["refs"][0]
            run, _ = db.create_run(
                session_id=session.id, owner_id=user.id, project_id=session.project_id,
                work_item_id=ref["itemId"], mode="exec",
                workspace=f"projects/{session.project_id}",
                idempotency_key=kwargs["idempotency_key"],
            )
            path = settings.WORKSPACE_ROOT / run.workspace / "report.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# verified", encoding="utf-8")
            db.upsert_artifact(
                run_id=run.id, path="report.md", full_path=path, source_tool="write_file",
            )
            db.set_run_status(run.id, "completed")
            yield "event: done\ndata: {}\n\n"

        with patch.object(work_item_runner.runtime, "run_chat", side_effect=completed_run):
            result = await work_items_router.execute_item(
                self.item.id, work_items_router.ExecuteWorkItemBody(idempotency_key="request-1"),
                authorization="",
            )
            launch, created = result["launch"], result["created"]
            task = work_item_runner._tasks[launch["id"]]
            await task
            replay_result = await work_items_router.execute_item(
                self.item.id, work_items_router.ExecuteWorkItemBody(idempotency_key="request-1"),
                authorization="",
            )
            replay, replay_created = replay_result["launch"], replay_result["created"]

        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(launch["id"], replay["id"])
        delivery = work_items_router.get_item_delivery(self.item.id)
        self.assertTrue(delivery["can_write"])
        self.assertEqual(1, len(delivery["runs"]))
        self.assertEqual(1, len(delivery["runs"][0]["artifacts"]))
        run = db.get_run(delivery["runs"][0]["id"])
        self.assertEqual(self.item.id, run.work_item_id)
        self.assertEqual("Owner", run.permission_snapshot["project_role"])
        self.assertEqual("doing", db.get_work_item(self.item.id).status)

        result = await work_items_router.accept_item_delivery(
            self.item.id, work_items_router.AcceptWorkItemDeliveryBody(run_id=run.id),
            authorization="",
        )
        self.assertTrue(result["ok"])
        self.assertEqual("done", db.get_work_item(self.item.id).status)
        self.assertEqual("accepted", db.get_run(run.id).status)
        self.assertEqual("accepted", db.list_artifacts(run.id)[0].acceptance_status)

    async def test_viewer_reads_delivery_but_cannot_launch_or_accept(self) -> None:
        viewer = db.create_user(name="viewer", password="pw", role=Role.VIEWER)
        db.add_project_member(self.project.id, viewer.id, Role.VIEWER)
        set_current_user_id(viewer.id)
        delivery = work_items_router.get_item_delivery(self.item.id)
        self.assertFalse(delivery["can_write"])
        with self.assertRaises(HTTPException) as launch_error:
            await work_items_router.execute_item(
                self.item.id, work_items_router.ExecuteWorkItemBody(idempotency_key="viewer"),
                authorization="",
            )
        self.assertEqual(403, launch_error.exception.status_code)

        stranger = db.create_user(name="stranger", password="pw")
        set_current_user_id(stranger.id)
        with self.assertRaises(HTTPException) as read_error:
            work_items_router.get_item_delivery(self.item.id)
        self.assertEqual(404, read_error.exception.status_code)

    async def test_expired_worker_attempt_creates_linked_retry_run(self) -> None:
        launch, _ = db.create_work_item_launch(
            work_item_id=self.item.id, owner_id=LOCAL_USER_ID,
            idempotency_key=f"work-item:{self.item.id}:recover",
        )
        session = db.create_session(
            owner_id=LOCAL_USER_ID, title="recover", kind="projexec", project_id=self.project.id,
        )
        launch = db.attach_work_item_launch_session(launch["id"], session.id)
        first_run, _ = db.create_run(
            session_id=session.id, owner_id=LOCAL_USER_ID, project_id=self.project.id,
            work_item_id=self.item.id, mode="exec", workspace=f"projects/{self.project.id}",
            idempotency_key=launch["idempotency_key"],
        )
        db.set_run_status(
            first_run.id, "failed", error_code="worker_restarted", error_message="interrupted",
        )
        job, _ = job_store.enqueue(
            owner_id=LOCAL_USER_ID, kind=work_item_runner.JOB_KIND, entity_id=launch["id"],
            idempotency_key=f"work-item-launch:{launch['id']}", max_attempts=3,
        )
        base = time.time() + 1
        job_store.claim(job["id"], "old", base, 5)
        job_store.recover_expired(base + 6)
        recovered = job_store.claim(job["id"], "new", base + 6, 5)

        async def completed_retry(session_arg, user, _prompt, **kwargs):
            self.assertEqual(first_run.id, kwargs["retry_of"])
            run, created = db.create_run(
                session_id=session_arg.id, owner_id=user.id, project_id=session_arg.project_id,
                work_item_id=self.item.id, mode="exec", workspace=f"projects/{self.project.id}",
                idempotency_key=kwargs["idempotency_key"], retry_of=kwargs["retry_of"],
            )
            self.assertTrue(created)
            db.set_run_status(run.id, "completed")
            yield "event: done\ndata: {}\n\n"

        with patch.object(work_item_runner.runtime, "run_chat", side_effect=completed_retry):
            await work_item_runner._execute_job(recovered)
        job_store.finish_success(job["id"], "new")
        saved = db.get_work_item_launch(launch["id"])
        retry_run = db.get_run(saved["run_id"])
        self.assertEqual("completed", saved["status"])
        self.assertEqual(first_run.id, retry_run.retry_of)
        self.assertEqual("succeeded", job_store.get(job["id"])["status"])

    async def test_acceptance_rolls_back_when_artifact_validation_failed(self) -> None:
        session = db.create_session(
            owner_id=LOCAL_USER_ID, title="invalid", kind="projexec", project_id=self.project.id,
        )
        run, _ = db.create_run(
            session_id=session.id, owner_id=LOCAL_USER_ID, project_id=self.project.id,
            work_item_id=self.item.id, mode="exec", workspace=f"projects/{self.project.id}",
        )
        path = settings.WORKSPACE_ROOT / run.workspace / "bad.txt"
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text("bad", encoding="utf-8")
        artifact = db.upsert_artifact(
            run_id=run.id, path="bad.txt", full_path=path, source_tool="write_file",
            validation={"passed": False},
        )
        db.get_conn().execute(
            "UPDATE artifacts SET validation_status='failed' WHERE id=?", (artifact.id,)
        )
        db.get_conn().commit(); db.set_run_status(run.id, "completed")
        with self.assertRaisesRegex(ValueError, "invalid artifacts"):
            db.accept_work_item_delivery(self.item.id, run.id, LOCAL_USER_ID)
        self.assertEqual("todo", db.get_work_item(self.item.id).status)
        self.assertEqual("completed", db.get_run(run.id).status)
        self.assertEqual("pending", db.get_artifact(artifact.id).acceptance_status)

    async def test_server_timeline_outbox_contains_metadata_only(self) -> None:
        db.get_conn().execute(
            "UPDATE projects SET origin='server' WHERE id=?", (self.project.id,)
        )
        db.get_conn().commit()
        old_url = settings.AGENTMATE_SERVER_URL
        old_upload = settings.AGENTMATE_SERVER_TIMELINE_UPLOAD
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        settings.AGENTMATE_SERVER_TIMELINE_UPLOAD = True
        try:
            self.assertTrue(server_sync.enqueue_work_item_event(
                project_id=self.project.id, work_item_id=self.item.id,
                launch_id="launch-id", actor_id=LOCAL_USER_ID,
                status="completed", artifact_count=2,
            ))
        finally:
            settings.AGENTMATE_SERVER_URL = old_url
            settings.AGENTMATE_SERVER_TIMELINE_UPLOAD = old_upload
        pending = db.list_pending_outbox()
        self.assertEqual(1, len(pending))
        payload = pending[0]["payload"]
        self.assertEqual({"kind", "title", "summary", "ext_id"}, set(payload))
        self.assertEqual("", payload["summary"])
        self.assertNotIn("prompt", json.dumps(payload).lower())
        self.assertNotIn("secret", json.dumps(payload).lower())
        self.assertNotIn("private", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main()
