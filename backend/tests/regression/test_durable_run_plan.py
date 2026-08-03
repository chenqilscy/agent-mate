"""Durable RunPlan state, recovery and promotion coverage (WB-385)."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from agent import runtime, skill_usage, tools  # noqa: E402
from agent.execution_policy import ExecutionAuthorization  # noqa: E402
from agent.tool_execution import execute_tool  # noqa: E402
from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import runs as runs_router, sessions as sessions_router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class DurableRunPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        self.project = db.create_project(owner_id=LOCAL_USER_ID, name="RunPlan")
        self.session = db.create_session(
            owner_id=LOCAL_USER_ID, title="durable plan", kind="projexec",
            project_id=self.project.id,
        )
        self.run, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID,
            project_id=self.project.id, mode="exec",
            workspace=f"projects/{self.project.id}",
        )
        skill_usage.set_context(LOCAL_USER_ID, self.run.id)
        set_current_user_id(LOCAL_USER_ID)

    def tearDown(self) -> None:
        set_current_user_id(None)
        skill_usage.clear_context()
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        self.tmp.cleanup()

    def _execute_update(self, args: dict) -> tools.ToolOutcome:
        return asyncio.run(execute_tool(
            tools.update_plan, args, asyncio.Event(),
            authorization=ExecutionAuthorization(owner_id=LOCAL_USER_ID),
        ))

    def test_worker_persists_stable_idempotent_snapshot_and_patch(self) -> None:
        first = self._execute_update({"todos": ["分析现状", "[~] 实现修复", "[!] 等待外部输入"]})
        persisted = db.get_run(self.run.id)
        self.assertEqual("plan_snapshot", first.trace[0]["kind"])
        self.assertEqual(1, persisted.plan_version)
        self.assertEqual(
            ["pending", "in_progress", "blocked"],
            [item["status"] for item in persisted.plan],
        )
        ids = [item["id"] for item in persisted.plan]

        replay = self._execute_update({
            "items": [
                {"id": item["id"], "title": item["title"], "status": item["status"],
                 "order": item["order"], "depends_on": item["depends_on"]}
                for item in persisted.plan
            ],
        })
        self.assertIn("未变化", replay.text)
        self.assertEqual(1, db.get_run(self.run.id).plan_version)

        patched = self._execute_update({
            "patches": [{"id": ids[0], "status": "completed"},
                        {"id": ids[1], "depends_on": [ids[0]]}],
        })
        persisted = db.get_run(self.run.id)
        self.assertEqual("plan_patch", patched.trace[0]["kind"])
        self.assertEqual(2, persisted.plan_version)
        self.assertEqual("completed", persisted.plan[0]["status"])
        self.assertEqual([ids[0]], persisted.plan[1]["depends_on"])
        self.assertEqual(ids, [item["id"] for item in persisted.plan])
        self.assertIn("event: plan_patch", runtime._trace_to_sse(patched.trace[0]))

    def test_retry_and_history_restore_materialized_plan(self) -> None:
        self._execute_update({"todos": ["第一步", "第二步"]})
        db.set_run_status(self.run.id, "failed", error_code="test")
        db.add_message(
            session_id=self.session.id, role="assistant", content="partial",
            actor="assistant", run_id=self.run.id,
        )
        retry, created = db.create_retry_run(self.run.id, LOCAL_USER_ID)
        self.assertTrue(created)
        self.assertEqual(db.get_run(self.run.id).plan, retry.plan)
        self.assertEqual(db.get_run(self.run.id).plan_version, retry.plan_version)

        response = sessions_router.get_messages(self.session.id)
        message = response["messages"][0]
        self.assertEqual(1, message["run_plan_version"])
        self.assertEqual(["第一步", "第二步"], [item["title"] for item in message["run_plan"]])
        self.assertEqual(self.project.id, message["run_project_id"])

    def test_plan_item_promotes_to_project_work_item_idempotently(self) -> None:
        self._execute_update({"items": [{"title": "形成验收报告", "status": "in_progress"}]})
        plan_item = db.get_run(self.run.id).plan[0]
        first = runs_router.promote_plan_item(self.run.id, plan_item["id"], authorization="")
        second = runs_router.promote_plan_item(self.run.id, plan_item["id"], authorization="")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["work_item"]["id"], second["work_item"]["id"])
        self.assertEqual("doing", db.get_work_item(first["work_item"]["id"]).status)
        self.assertEqual(
            first["work_item"]["id"], db.get_run(self.run.id).plan[0]["work_item_id"],
        )

    def test_frontend_reduces_plan_events_to_current_state_and_exposes_promotion(self) -> None:
        store = (ROOT / "src/stores/chatStore.ts").read_text(encoding="utf-8")
        trace = (ROOT / "src/components/chat/TraceStream.tsx").read_text(encoding="utf-8")
        self.assertIn("case 'plan_snapshot':", store)
        self.assertIn("case 'plan_patch':", store)
        self.assertIn("run_plan_version", store)
        self.assertIn("promoteRunPlanItem", trace)
        self.assertIn("提升为任务", trace)


if __name__ == "__main__":
    unittest.main()
