"""Immediate LLM stream cleanup on stop (WB-276)."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime  # noqa: E402
from agent.llm import Delta  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class NoopObservation:
    def update(self, **_kwargs):
        pass


@contextmanager
def noop_observation(**_kwargs):
    yield NoopObservation()


class LlmStreamCleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="stream cleanup")

    def tearDown(self) -> None:
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

    def test_stop_break_immediately_closes_llm_generator(self) -> None:
        closed = False

        async def fake_stream(*_args, **_kwargs):
            nonlocal closed
            try:
                self.assertTrue(runtime.request_stop(self.session.id))
                yield Delta(content="must not be consumed")
            finally:
                closed = True

        async def collect() -> None:
            async for _ in runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "stop now",
            ):
                pass

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
        ):
            asyncio.run(collect())

        self.assertTrue(closed)
        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual("cancelled", run.status)
        self.assertFalse(runtime.request_stop(self.session.id))

    def test_client_disconnect_closes_stream_and_unregisters_run(self) -> None:
        closed = False

        async def fake_stream(*_args, **_kwargs):
            nonlocal closed
            try:
                yield Delta(content="partial")
                await asyncio.Event().wait()
            finally:
                closed = True

        async def disconnect_after_first_text() -> None:
            stream = runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "disconnect now",
            )
            async for chunk in stream:
                if "event: text" in chunk:
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
        ):
            asyncio.run(disconnect_after_first_text())

        self.assertTrue(closed)
        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertIn(run.status, {"paused", "cancelled"})
        self.assertFalse(runtime.request_stop(self.session.id))


if __name__ == "__main__":
    unittest.main()
