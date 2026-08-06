"""WB-422: local idea capture, processing provenance and explicit settlement."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import sandbox, workspace_memory  # noqa: E402
from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import ideas as router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class ProjectIdeaInboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = sandbox.WORKSPACE_BASE
        self.old_default = sandbox.DEFAULT_ROOT
        self._close()
        root = Path(self.tmp.name)
        settings.DB_PATH = root / "app.db"
        sandbox.WORKSPACE_BASE = root / "workspace"
        sandbox.DEFAULT_ROOT = sandbox.WORKSPACE_BASE / "default"
        db.init_db()
        set_current_user_id(None)
        self.project = db.create_project(owner_id=LOCAL_USER_ID, name="Idea project")

    def tearDown(self) -> None:
        self._close()
        settings.DB_PATH = self.old_db
        sandbox.WORKSPACE_BASE = self.old_workspace
        sandbox.DEFAULT_ROOT = self.old_default
        set_current_user_id(None)
        self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()

    def _create(self, content: str, project_id: str | None = None) -> dict:
        return router.create_idea(router.CreateBody(
            content=content, project_id=project_id,
        ))["idea"]

    def test_message_capture_is_idempotent_owner_scoped_and_persistent(self) -> None:
        session = db.create_session(owner_id=LOCAL_USER_ID, title="source")
        message = db.add_message(
            session_id=session.id, role="assistant", content="真实消息正文",
            actor="assistant",
        )
        body = router.CreateBody(
            content="客户端不能伪造这段内容", source_type="message",
            source_session_id=session.id, source_message_id=message.id,
        )
        first = router.create_idea(body)
        second = router.create_idea(body)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["idea"]["id"], second["idea"]["id"])
        self.assertEqual("真实消息正文", first["idea"]["content"])
        self.assertEqual(message.id, first["idea"]["source_message_id"])

        other = db.create_user(name="other", password="test-password")
        set_current_user_id(other.id)
        self.assertEqual([], router.list_ideas()["ideas"])

        set_current_user_id(None)
        self._close()
        db.init_db()
        self.assertEqual(first["idea"]["id"], router.list_ideas()["ideas"][0]["id"])

    def test_project_role_gate_and_same_scope_relations(self) -> None:
        first = self._create("first", self.project.id)
        second = self._create("second", self.project.id)
        detail = router.add_relation(first["id"], router.RelationBody(
            target_idea_id=second["id"], relation="related",
        ))
        self.assertEqual(1, len(detail["relations"]))
        # Symmetric reverse creation is canonicalized and remains idempotent.
        reverse = router.add_relation(second["id"], router.RelationBody(
            target_idea_id=first["id"], relation="related",
        ))
        self.assertEqual(1, len(reverse["relations"]))

        moved = router.update_idea(first["id"], router.UpdateBody(project_id=None))
        self.assertEqual("inbox", moved["status"])
        self.assertEqual([], moved["relations"])
        self.assertEqual([], router.get_idea(second["id"])["relations"])

        viewer = db.create_user(name="viewer", password="test-password")
        db.add_project_member(self.project.id, viewer.id, Role.VIEWER)
        set_current_user_id(viewer.id)
        with self.assertRaises(HTTPException) as denied:
            router.create_idea(router.CreateBody(content="viewer write", project_id=self.project.id))
        self.assertEqual(403, denied.exception.status_code)

    def test_processing_result_requires_explicit_apply(self) -> None:
        idea = self._create("raw idea", self.project.id)
        session = db.create_session(
            owner_id=LOCAL_USER_ID, title="processing", kind="projexec",
            project_id=self.project.id,
        )
        db.add_message(session_id=session.id, role="assistant", content="整理后的建议稿", actor="assistant")
        linked = router.update_idea(idea["id"], router.UpdateBody(processing_session_id=session.id))
        self.assertEqual("", linked["processed_content"])
        applied = router.apply_processing(idea["id"])
        self.assertEqual("整理后的建议稿", applied["processed_content"])

    def test_settlement_is_explicit_idempotent_and_keeps_targets_real(self) -> None:
        task_idea = self._create("task body", self.project.id)
        first_task = router.settle_idea(task_idea["id"], router.SettleBody(kind="work_item"), "")
        second_task = router.settle_idea(task_idea["id"], router.SettleBody(kind="work_item"), "")
        self.assertTrue(first_task["created"])
        self.assertFalse(second_task["created"])
        self.assertEqual(first_task["target"]["id"], second_task["target"]["id"])
        self.assertEqual(1, len(db.list_work_items(self.project.id)))
        self.assertEqual(task_idea["id"], db.list_work_items(self.project.id)[0].custom_fields["idea_id"])

        decision_idea = self._create("decision body", self.project.id)
        decision = router.settle_idea(decision_idea["id"], router.SettleBody(kind="decision"), "")
        self.assertEqual("decision", decision["idea"]["settled_type"])
        records = db.list_project_governance(self.project.id)
        self.assertEqual(f"idea:{decision_idea['id']}", records[0]["evidence_label"])

        memory_idea = self._create("memory body", self.project.id)
        self.assertEqual("", workspace_memory.read_curated(self.project.id))
        preview = router.memory_preview(memory_idea["id"])
        self.assertIn("memory body", preview["proposed"])
        memory = router.settle_idea(memory_idea["id"], router.SettleBody(
            kind="memory", memory_base_sha256=preview["base_sha256"],
        ), "")
        self.assertEqual("memory", memory["idea"]["settled_type"])
        self.assertIn(f"agentmate-idea:{memory_idea['id']}", workspace_memory.read_curated(self.project.id))

    def test_server_settlement_failure_does_not_fake_success(self) -> None:
        db.get_conn().execute("UPDATE projects SET origin='server' WHERE id=?", (self.project.id,))
        db.get_conn().commit()
        idea = self._create("server task", self.project.id)
        with patch.object(router.work_items, "_server_write_token", return_value="token"), \
             patch.object(router.work_items.server_client, "create_work_item", return_value=None):
            with self.assertRaises(HTTPException) as failed:
                router.settle_idea(idea["id"], router.SettleBody(kind="work_item"), "Bearer token")
        self.assertEqual(503, failed.exception.status_code)
        current = router.get_idea(idea["id"])
        self.assertEqual("active", current["status"])
        self.assertEqual("", current["settled_type"])


if __name__ == "__main__":
    unittest.main()
