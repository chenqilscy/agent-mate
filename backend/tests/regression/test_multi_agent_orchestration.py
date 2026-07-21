"""Multi-agent DAG validation and durable state regression (WB-258)."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from agent import orchestrator
from config import settings
from storage import db, orchestration_store as store
from storage.models import LOCAL_USER_ID


class MultiAgentOrchestrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        settings.DB_PATH = Path(self.tmp.name) / "agentmate.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        db._local = threading.local()
        db.init_db()
        store.ensure_tables()
        self.team = orchestrator.resolve_team("深度研究团队")
        self.assertIsNotNone(self.team)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        db._local = threading.local()
        self.tmp.cleanup()

    def test_plan_requires_known_experts_valid_dependencies_and_acyclic_graph(self) -> None:
        members = self.team["members"]
        valid = {"tasks": [
            {"id": "sources", "title": "资料", "instruction": "核对资料", "expert_slug": members[1]["expert_slug"], "depends_on": []},
            {"id": "analysis", "title": "分析", "instruction": "分析证据", "expert_slug": members[2]["expert_slug"], "depends_on": ["sources"]},
        ]}
        plan = orchestrator.validate_plan(valid, self.team, 5)
        self.assertEqual(["sources"], plan[1]["depends_on"])
        cyclic = {"tasks": [
            {**valid["tasks"][0], "depends_on": ["analysis"]},
            valid["tasks"][1],
        ]}
        with self.assertRaisesRegex(ValueError, "cyclic"):
            orchestrator.validate_plan(cyclic, self.team, 5)
        unknown = {"tasks": [{**valid["tasks"][0], "expert_slug": "missing"}]}
        with self.assertRaisesRegex(ValueError, "expert"):
            orchestrator.validate_plan(unknown, self.team, 5)
        routed = orchestrator.build_role_plan(self.team, 2)
        self.assertEqual(2, len(routed))
        self.assertNotEqual(routed[0]["expert_slug"], routed[1]["expert_slug"])
        self.assertTrue(all(not item["depends_on"] for item in routed))

    def test_idempotent_orchestration_and_node_cost_rollup(self) -> None:
        first, created = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="研究目标",
            idempotency_key="stable-key", max_nodes=6, max_parallel=2, max_total_tokens=12000,
        )
        second, duplicate = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="不会覆盖",
            idempotency_key="stable-key", max_nodes=6, max_parallel=2, max_total_tokens=12000,
        )
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first["id"], second["id"])
        node = store.add_node(
            first["id"], node_key="research", title="研究", role="分析师",
            expert_slug="data-report-analyst", instruction="分析", depends_on=[],
        )
        session = db.create_session(owner_id=LOCAL_USER_ID, title="member")
        run, _ = db.create_run(
            session_id=session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="ask", idempotency_key="member-run",
        )
        store.start_node(first["id"], node["node_key"], session.id)
        store.finish_node(
            first["id"], node["node_key"], status="completed", run_id=run.id,
            output="真实成员输出", prompt_tokens=90, completion_tokens=30,
        )
        saved = store.get(first["id"], LOCAL_USER_ID)
        self.assertEqual(120, saved["prompt_tokens"] + saved["completion_tokens"])
        self.assertEqual(run.id, saved["nodes"][0]["run_id"])
        self.assertEqual("真实成员输出", saved["nodes"][0]["output"])

    def test_process_recovery_marks_nonterminal_work_failed(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="产品战略团队", goal="目标",
            idempotency_key=None, max_nodes=5, max_parallel=2, max_total_tokens=8000,
        )
        store.ensure_tables()
        recovered = store.get(item["id"], LOCAL_USER_ID)
        self.assertEqual("failed", recovered["status"])
        self.assertEqual("process_restarted", recovered["error"])

    def test_attempts_preserve_retry_trace_and_aggregate_cost(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="目标",
            idempotency_key=None, max_nodes=5, max_parallel=2, max_total_tokens=10000,
        )
        store.add_node(
            item["id"], node_key="planner", title="规划", role="主编",
            expert_slug="long-form-editor", instruction="规划", depends_on=[],
        )
        first_session = db.create_session(owner_id=LOCAL_USER_ID, title="first")
        first_run, _ = db.create_run(
            session_id=first_session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="ask", idempotency_key="attempt-1",
        )
        first = store.start_attempt(item["id"], "planner", first_session.id)
        store.finish_attempt(
            first["id"], status="failed", run_id=first_run.id, error="LLM 429",
            prompt_tokens=40, completion_tokens=0,
        )
        second_session = db.create_session(owner_id=LOCAL_USER_ID, title="second")
        second_run, _ = db.create_run(
            session_id=second_session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="ask", idempotency_key="attempt-2",
        )
        second = store.start_attempt(item["id"], "planner", second_session.id)
        store.finish_attempt(
            second["id"], status="completed", run_id=second_run.id,
            prompt_tokens=80, completion_tokens=20,
        )
        store.finish_node(
            item["id"], "planner", status="completed", run_id=second_run.id, output="合法计划",
        )
        saved = store.get(item["id"], LOCAL_USER_ID)
        node = saved["nodes"][0]
        self.assertEqual(2, len(node["attempts"]))
        self.assertEqual(140, node["prompt_tokens"] + node["completion_tokens"])
        self.assertEqual(140, saved["prompt_tokens"] + saved["completion_tokens"])


if __name__ == "__main__":
    unittest.main()
