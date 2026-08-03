"""Runtime evidence for explicit context-compaction degradation (WB-384)."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from agent import runtime, session_context  # noqa: E402
from agent.llm import Delta  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class NoopObservation:
    def update(self, **_kwargs) -> None:
        pass


@contextmanager
def noop_observation(**_kwargs):
    yield NoopObservation()


class ContextCompactionDegradedEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="degraded")

    def tearDown(self) -> None:
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        self.tmp.cleanup()

    def test_runtime_emits_and_persists_degraded_context_evidence(self) -> None:
        result = session_context.ContextBuildResult(
            messages=[{"role": "system", "content": "system"}, {"role": "user", "content": "question"}],
            compaction_degraded=True,
            compaction_reason="summary_timeout",
            degraded_excerpt_messages=2,
        )

        async def fake_stream(*_args, **_kwargs):
            yield Delta(content="已按降级上下文继续。")

        async def collect() -> str:
            return "".join([
                chunk async for chunk in runtime.run_chat(
                    self.session, db.get_user(LOCAL_USER_ID), "继续",
                )
            ])

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime.session_context, "build_llm_context", new=AsyncMock(return_value=result)),
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
        ):
            payload = asyncio.run(collect())

        self.assertIn("event: context_degraded", payload)
        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual("completed", run.status)
        self.assertEqual({
            "degraded": True,
            "reason": "summary_timeout",
            "excerpt_messages": 2,
            "retry_on_next_turn": True,
        }, run.checkpoint["context_compaction"])
        assistant = next(item for item in db.list_messages(self.session.id) if item.role == "assistant")
        self.assertEqual("context_degraded", assistant.trace[0]["kind"])

        store = (ROOT / "src/stores/chatStore.ts").read_text(encoding="utf-8")
        trace = (ROOT / "src/components/chat/TraceStream.tsx").read_text(encoding="utf-8")
        self.assertIn("case 'context_degraded'", store)
        self.assertIn("较早对话压缩失败", trace)


if __name__ == "__main__":
    unittest.main()
