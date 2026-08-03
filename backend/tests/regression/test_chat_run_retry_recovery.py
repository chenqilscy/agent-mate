"""Persisted chat Run recovery contract (WB-358)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from auth.middleware import AuthMiddleware  # noqa: E402
from config import settings  # noqa: E402
from routers import sessions  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ChatRunRetryRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="retry")
        self.original, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="exec", workspace="default",
        )
        db.set_run_status(self.original.id, "failed", error_code="llm_error")
        db.add_message(
            session_id=self.session.id, role="assistant", content="partial",
            actor="assistant", run_id=self.original.id, error="provider unavailable",
        )

        token = db.create_token(LOCAL_USER_ID)
        db.set_server_identity(LOCAL_USER_ID, token)
        app = FastAPI()
        app.add_middleware(AuthMiddleware)
        app.include_router(sessions.router)
        self.client = TestClient(app)
        self.auth = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        self.client.close()
        self._close_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        db.close_thread_connection()

    def test_reload_exposes_retryable_run_and_retry_link_is_persisted(self) -> None:
        response = self.client.get(
            f"/api/sessions/{self.session.id}/messages", headers=self.auth,
        )
        self.assertEqual(200, response.status_code, response.text)
        message = response.json()["messages"][0]
        self.assertEqual(self.original.id, message["run_id"])
        self.assertEqual("failed", message["run_status"])
        self.assertEqual("provider unavailable", message["error"])

        retry, created = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="exec", workspace="default", retry_of=self.original.id,
        )
        self.assertTrue(created)
        self.assertEqual(self.original.id, db.get_run(retry.id).retry_of)

    def test_frontend_wires_retry_source_and_only_retryable_statuses(self) -> None:
        store = (ROOT / "src/stores/chatStore.ts").read_text(encoding="utf-8")
        message_list = (ROOT / "src/components/chat/MessageList.tsx").read_text(encoding="utf-8")
        self.assertIn("retryOf,", store)
        self.assertIn("await get().send(userMessage.content, message.runId)", store)
        self.assertIn("['failed', 'cancelled', 'paused']", store)
        self.assertIn("重试本次运行", message_list)

    def test_reload_returns_sanitized_pending_question_for_retry_only(self) -> None:
        waiting, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="exec", workspace="default",
        )
        db.set_run_status(waiting.id, "waiting_approval", checkpoint={
            "kind": "ask_user",
            "questions": [{"q": "继续吗？", "options": ["继续", "停止"]}],
            "source": "agent",
            "tool_call_id": "internal-call-id",
        })
        db.set_run_status(
            waiting.id, "paused",
            checkpoint={**db.get_run(waiting.id).checkpoint, "reason": "stream_disconnected"},
        )
        db.add_message(
            session_id=self.session.id, role="assistant", content="",
            actor="assistant", run_id=waiting.id, error="运行已暂停，可重试",
        )

        response = self.client.get(
            f"/api/sessions/{self.session.id}/messages", headers=self.auth,
        )
        self.assertEqual(200, response.status_code, response.text)
        item = next(message for message in response.json()["messages"] if message["run_id"] == waiting.id)
        self.assertEqual("paused", item["run_status"])
        self.assertEqual("retry_required", item["pending_question"]["recovery"])
        self.assertEqual("继续吗？", item["pending_question"]["questions"][0]["q"])
        self.assertNotIn("tool_call_id", item["pending_question"])

        store = (ROOT / "src/stores/chatStore.ts").read_text(encoding="utf-8")
        message_list = (ROOT / "src/components/chat/MessageList.tsx").read_text(encoding="utf-8")
        self.assertIn("pendingQuestion: m.pending_question", store)
        self.assertIn("上次运行在等待回答时中断", message_list)
        self.assertIn("原等待流已结束", message_list)


if __name__ == "__main__":
    unittest.main()
