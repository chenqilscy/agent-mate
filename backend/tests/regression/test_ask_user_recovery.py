"""Durable ask_user checkpoint and disconnect cleanup contract (WB-381)."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime  # noqa: E402
from agent.llm import Delta, ToolCallDelta  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class NoopObservation:
    def update(self, **_kwargs) -> None:
        pass


@contextmanager
def noop_observation(**_kwargs):
    yield NoopObservation()


class AskUserRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="ask recovery")

    def tearDown(self) -> None:
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        runtime._answers.clear()
        runtime._session_runs.clear()
        runtime._stop_events.clear()
        self.tmp.cleanup()

    def test_disconnect_after_question_preserves_checkpoint_and_unregisters_waiter(self) -> None:
        questions = [{"q": "继续执行吗？", "options": ["继续", "停止"]}]

        async def fake_stream(*_args, **_kwargs):
            yield Delta(tool_calls=[ToolCallDelta(
                index=0, id="call-ask", name="ask_user",
                arguments=json.dumps({"questions": questions}, ensure_ascii=False),
            )])

        async def disconnect() -> None:
            stream = runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "需要确认",
            )
            async for chunk in stream:
                if "event: ask_user" in chunk:
                    await stream.aclose()
                    break

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            asyncio.run(disconnect())

        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual("paused", run.status)
        self.assertEqual("ask_user", run.checkpoint["kind"])
        self.assertEqual(questions, run.checkpoint["questions"])
        self.assertEqual("stream_disconnected", run.checkpoint["reason"])
        self.assertNotIn(run.id, runtime._answers)
        self.assertNotIn(run.id, runtime._stop_events)
        self.assertNotIn(self.session.id, runtime._session_runs)
        messages = db.list_messages(self.session.id)
        self.assertEqual(1, len([item for item in messages if item.role == "assistant"]))

    def test_live_answer_clears_checkpoint_and_finishes_normally(self) -> None:
        questions = [{"q": "继续执行吗？", "options": ["继续", "停止"]}]

        async def fake_stream(messages, **_kwargs):
            if not any(message.get("role") == "tool" for message in messages):
                yield Delta(tool_calls=[ToolCallDelta(
                    index=0, id="call-ask", name="ask_user",
                    arguments=json.dumps({"questions": questions}, ensure_ascii=False),
                )])
            else:
                yield Delta(content="继续执行。")

        async def answer_and_collect() -> str:
            chunks = []
            async for chunk in runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "需要确认",
            ):
                chunks.append(chunk)
                if "event: ask_user" in chunk:
                    run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
                    self.assertEqual("waiting_approval", run.status)
                    self.assertEqual(questions, run.checkpoint["questions"])
                    self.assertTrue(runtime.submit_answers(self.session.id, ["继续"]))
            return "".join(chunks)

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            payload = asyncio.run(answer_and_collect())

        self.assertIn("event: qa_summary", payload)
        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual("completed", run.status)
        self.assertEqual({}, run.checkpoint)
        self.assertFalse(runtime._answers)


if __name__ == "__main__":
    unittest.main()
