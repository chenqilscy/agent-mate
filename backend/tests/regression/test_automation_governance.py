"""Durable automation fire, retry, DLQ and token-budget coverage (WB-251)."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime, scheduler  # noqa: E402
from agent.llm import Delta  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class AutomationGovernanceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()

    def tearDown(self) -> None:
        scheduler._running.clear()
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

    def _automation(self, **overrides):
        values = {
            "owner_id": LOCAL_USER_ID, "name": "日报", "prompt": "生成日报",
            "max_attempts": 2, "retry_backoff_sec": 1,
            "notify_policy": "failure,recovery", "timeout_sec": 5,
        }
        values.update(overrides)
        return db.create_automation(**values)

    async def test_normal_stream_end_with_failed_run_retries_then_enters_dlq_once(self) -> None:
        auto = self._automation()
        fire, created = db.create_automation_fire(
            automation_id=auto.id, owner_id=auto.owner_id, fire_key="scheduled:1",
            trigger_kind="scheduled", planned_at=0, max_attempts=auto.max_attempts,
        )
        replay, replay_created = db.create_automation_fire(
            automation_id=auto.id, owner_id=auto.owner_id, fire_key="scheduled:1",
            trigger_kind="scheduled", planned_at=0, max_attempts=auto.max_attempts,
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(fire.id, replay.id)

        async def failed_stream(session, user, prompt, **kwargs):
            run, _ = db.create_run(
                session_id=session.id, owner_id=user.id, project_id=session.project_id,
                mode="exec", idempotency_key=kwargs["idempotency_key"],
                retry_of=kwargs.get("retry_of"),
            )
            db.update_run_runtime(run.id, prompt_tokens=11, completion_tokens=3)
            db.set_run_status(run.id, "failed", error_code="llm_error", error_message="401")
            yield "event: error\ndata: {}\n\n"

        with patch.object(scheduler.runtime, "run_chat", side_effect=failed_stream):
            await scheduler._execute_fire(fire.id)
            first = db.get_automation_fire(fire.id)
            self.assertEqual("retry_wait", first.status)
            self.assertEqual(1, first.attempt)
            db.get_conn().execute(
                "UPDATE automation_fires SET next_attempt_at=0 WHERE id=?", (fire.id,)
            )
            db.get_conn().commit()
            await scheduler._execute_fire(fire.id)

        final = db.get_automation_fire(fire.id)
        self.assertEqual("dead_letter", final.status)
        self.assertEqual(2, final.attempt)
        self.assertEqual(28, final.prompt_tokens + final.completion_tokens)
        runs = list(reversed(db.list_runs(LOCAL_USER_ID, session_id=final.session_id)))
        self.assertEqual(2, len(runs))
        self.assertEqual(runs[0].id, runs[1].retry_of)
        self.assertEqual("error", db.get_session(final.session_id).run_status)
        notices = db.list_notifications(LOCAL_USER_ID)
        self.assertEqual(1, len(notices))
        self.assertNotIn("生成日报", notices[0]["body"])
        self.assertFalse(db.mark_automation_fire_notified(final.id, "failure"))

        recovery, _ = db.create_automation_fire(
            automation_id=auto.id, owner_id=auto.owner_id, fire_key="scheduled:2",
            trigger_kind="scheduled", planned_at=0, max_attempts=auto.max_attempts,
        )

        async def success_stream(session, user, prompt, **kwargs):
            run, _ = db.create_run(
                session_id=session.id, owner_id=user.id, project_id=session.project_id,
                mode="exec", idempotency_key=kwargs["idempotency_key"],
            )
            db.set_run_status(run.id, "completed")
            yield "event: done\ndata: {}\n\n"

        with patch.object(scheduler.runtime, "run_chat", side_effect=success_stream):
            await scheduler._execute_fire(recovery.id)
        self.assertEqual("succeeded", db.get_automation_fire(recovery.id).status)
        notices = db.list_notifications(LOCAL_USER_ID)
        self.assertEqual(2, len(notices))
        self.assertIn("已恢复", notices[0]["title"])

    async def test_runtime_token_budget_is_terminal_run_evidence(self) -> None:
        session = db.create_session(owner_id=LOCAL_USER_ID, title="budget")

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def over_budget(_messages, **_kwargs):
            yield Delta(content="partial", usage={"prompt_tokens": 10, "completion_tokens": 5})

        async def collect():
            return [chunk async for chunk in runtime.run_chat(
                session, db.get_user(LOCAL_USER_ID), "受限任务", max_total_tokens=5,
            )]

        with (
            patch.object(runtime, "stream_chat", side_effect=over_budget),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=settings.WORKSPACE_ROOT / "default"),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            chunks = await collect()

        run = db.list_runs(LOCAL_USER_ID, session_id=session.id)[0]
        self.assertEqual("failed", run.status)
        self.assertEqual("token_budget_exceeded", run.error_code)
        self.assertEqual(15, run.prompt_tokens + run.completion_tokens)
        self.assertIn("token", "".join(chunks).lower())

    async def test_stale_running_fire_is_recovered_after_process_restart(self) -> None:
        auto = self._automation(timeout_sec=1)
        fire, _ = db.create_automation_fire(
            automation_id=auto.id, owner_id=auto.owner_id, fire_key="scheduled:restart",
            trigger_kind="scheduled", planned_at=0, max_attempts=auto.max_attempts,
        )
        fire = db.claim_automation_fire(fire.id, 1)
        session = db.create_session(
            owner_id=auto.owner_id, title="restart", kind="automation",
            automation_id=auto.id, run_status="running",
        )
        db.attach_automation_fire_session(fire.id, session.id)
        run, _ = db.create_run(
            session_id=session.id, owner_id=auto.owner_id, project_id=None, mode="exec",
            idempotency_key=f"automation:{fire.id}:attempt:1",
        )
        db.get_conn().execute(
            "UPDATE automation_fires SET updated_at=0 WHERE id=?", (fire.id,)
        )
        db.get_conn().commit()

        recovered = db.recover_stale_automation_fires(2)
        self.assertEqual([fire.id], [item.id for item in recovered])
        self.assertEqual("retry_wait", recovered[0].status)
        self.assertEqual("failed", db.get_run(run.id).status)
        self.assertEqual("scheduler_restarted", db.get_run(run.id).error_code)


if __name__ == "__main__":
    unittest.main()
