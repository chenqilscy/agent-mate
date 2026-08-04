"""Multi-agent DAG validation and durable state regression (WB-258)."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import events, orchestrator
from config import settings
from routers import orchestrations as orchestration_router
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
        parallel = orchestrator.build_role_plan(self.team, 3)
        self.assertEqual(3, len(parallel))
        self.assertEqual(3, len({item["expert_slug"] for item in parallel}))

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

    def test_structured_handoff_preserves_run_and_artifact_evidence_outside_summary_budget(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="研究目标",
            idempotency_key=None, max_nodes=6, max_parallel=2, max_total_tokens=12000,
        )
        upstream = store.add_node(
            item["id"], node_key="upstream", title="上游", role="分析师",
            expert_slug="data-report-analyst", instruction="分析", depends_on=[],
        )
        downstream = store.add_node(
            item["id"], node_key="downstream", title="下游", role="主编",
            expert_slug="long-form-editor", instruction="综合", depends_on=["upstream"],
        )
        session = db.create_session(owner_id=LOCAL_USER_ID, title="handoff")
        run, _ = db.create_run(
            session_id=session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="ask", workspace="default", idempotency_key="handoff-run",
        )
        db.set_run_status(run.id, "completed")
        target = settings.WORKSPACE_ROOT / "default" / "evidence.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("authoritative evidence", encoding="utf-8")
        artifact = db.upsert_artifact(
            run_id=run.id, path="evidence.md", full_path=target,
            source_tool="test", kind="document", validation={"checked": True},
            is_primary=True,
        )
        handoff = orchestrator._build_handoff(
            run_id=run.id, status="completed", output="摘要" * 20000,
        )
        store.finish_node(
            item["id"], upstream["node_key"], status="completed", run_id=run.id,
            output="摘要" * 20000, handoff=handoff,
        )
        saved = store.get_node(item["id"], upstream["node_key"])
        self.assertEqual(1, saved["handoff"]["schema_version"])
        self.assertEqual(run.id, saved["handoff"]["run"]["id"])
        self.assertEqual(artifact.sha256, saved["handoff"]["artifacts"][0]["sha256"])
        context = orchestrator._dependency_context(downstream, [saved, downstream])
        self.assertIn(run.id, context)
        self.assertIn("evidence.md", context)
        self.assertIn(artifact.sha256, context)
        self.assertLess(len(context), len(saved["output"]))

    def test_process_recovery_preserves_completed_nodes_and_requeues_interrupted_node(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="产品战略团队", goal="目标",
            idempotency_key=None, max_nodes=5, max_parallel=2, max_total_tokens=8000,
        )
        completed = store.add_node(
            item["id"], node_key="completed", title="已完成", role="成员",
            expert_slug="data-report-analyst", instruction="完成", depends_on=[],
        )
        done_session = db.create_session(owner_id=LOCAL_USER_ID, title="done")
        done_attempt = store.start_attempt(item["id"], completed["node_key"], done_session.id)
        store.finish_attempt(done_attempt["id"], status="completed", run_id=None)
        store.finish_node(
            item["id"], completed["node_key"], status="completed", run_id=None, output="证据",
        )
        interrupted = store.add_node(
            item["id"], node_key="interrupted", title="中断", role="成员",
            expert_slug="data-report-analyst", instruction="继续", depends_on=["completed"],
        )
        running_session = db.create_session(owner_id=LOCAL_USER_ID, title="running")
        store.start_attempt(item["id"], interrupted["node_key"], running_session.id)
        store.set_status(item["id"], "running")
        store.prepare_resume(item["id"])
        recovered = store.get(item["id"], LOCAL_USER_ID)
        self.assertEqual("running", recovered["status"])
        by_key = {node["node_key"]: node for node in recovered["nodes"]}
        self.assertEqual("completed", by_key["completed"]["status"])
        self.assertEqual("pending", by_key["interrupted"]["status"])
        self.assertEqual("failed", by_key["interrupted"]["attempts"][0]["status"])
        self.assertEqual("worker_restarted", by_key["interrupted"]["attempts"][0]["error"])

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

    def test_detail_bulk_loads_attempts_without_node_n_plus_one(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="目标",
            idempotency_key=None, max_nodes=6, max_parallel=3, max_total_tokens=12000,
        )
        for index in range(3):
            key = f"member_{index}"
            store.add_node(
                item["id"], node_key=key, title=key, role="成员",
                expert_slug="data-report-analyst", instruction="分析", depends_on=[],
            )
            session = db.create_session(owner_id=LOCAL_USER_ID, title=key)
            attempt = store.start_attempt(item["id"], key, session.id)
            store.finish_attempt(attempt["id"], status="failed", run_id=None, error="failure")
        statements: list[str] = []
        conn = db.get_conn()
        conn.set_trace_callback(statements.append)
        try:
            saved = store.get(item["id"], LOCAL_USER_ID)
        finally:
            conn.set_trace_callback(None)
        self.assertEqual(3, len(saved["nodes"]))
        attempt_queries = [
            sql for sql in statements
            if sql.lstrip().upper().startswith("SELECT") and "orchestration_attempts" in sql
        ]
        self.assertEqual(1, len(attempt_queries), statements)

    def test_cancel_converges_parent_nodes_and_attempts(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="目标",
            idempotency_key=None, max_nodes=6, max_parallel=3, max_total_tokens=12000,
        )
        store.add_node(
            item["id"], node_key="active", title="执行", role="成员",
            expert_slug="data-report-analyst", instruction="分析", depends_on=[],
        )
        store.add_node(
            item["id"], node_key="pending", title="等待", role="成员",
            expert_slug="data-report-analyst", instruction="分析", depends_on=["active"],
        )
        session = db.create_session(owner_id=LOCAL_USER_ID, title="active")
        store.start_attempt(item["id"], "active", session.id)
        store.set_status(item["id"], "running")
        store.cancel_nonterminal(item["id"])
        saved = store.get(item["id"], LOCAL_USER_ID)
        self.assertEqual("cancelled", saved["status"])
        self.assertTrue(all(node["status"] == "cancelled" for node in saved["nodes"]))
        self.assertEqual("cancelled", saved["nodes"][0]["attempts"][0]["status"])

    def test_retry_deducts_actual_usage_from_node_budget(self) -> None:
        item, _ = store.create(
            owner_id=LOCAL_USER_ID, project_id=None, team_name="深度研究团队", goal="目标",
            idempotency_key=None, max_nodes=6, max_parallel=3, max_total_tokens=12000,
        )
        node = store.add_node(
            item["id"], node_key="member", title="执行", role="成员",
            expert_slug="data-report-analyst", instruction="分析", depends_on=[],
        )
        budgets: list[int] = []

        async def fake_run_chat(session, user, prompt, **kwargs):
            budgets.append(kwargs["max_total_tokens"])
            run, _ = db.create_run(
                session_id=session.id, owner_id=user.id, project_id=None, mode="ask",
                idempotency_key=kwargs["idempotency_key"],
            )
            if len(budgets) == 1:
                db.update_run_runtime(run.id, prompt_tokens=240, completion_tokens=60)
                db.set_run_status(run.id, "failed", error_code="llm_error", error_message="LLM 429")
                yield events.error("LLM 429")
            else:
                db.update_run_runtime(run.id, prompt_tokens=80, completion_tokens=20)
                db.set_run_status(run.id, "completed")
                yield events.text("完成")

        user = db.get_user(LOCAL_USER_ID)
        with patch.object(orchestrator.runtime, "run_chat", fake_run_chat), patch.object(
            orchestrator, "_retry_delay", return_value=0,
        ):
            result = asyncio.run(orchestrator._execute_node(item, user, node, "目标", token_budget=1000))
        self.assertEqual([1000, 700], budgets)
        self.assertEqual("completed", result["status"])
        self.assertEqual(400, result["prompt_tokens"] + result["completion_tokens"])

    def test_create_api_starts_scheduler_on_event_loop(self) -> None:
        started: list[str] = []

        def fake_start(orchestration_id, user, team):
            asyncio.get_running_loop()
            started.append(orchestration_id)

        body = orchestration_router.CreateBody(
            team_name="深度研究团队", goal="目标", idempotency_key="api-event-loop",
            max_nodes=5, max_parallel=3, max_total_tokens=6000,
        )
        with patch.object(orchestration_router.orchestrator, "start", fake_start):
            result = asyncio.run(orchestration_router.create(body))
        self.assertTrue(result["created"])
        self.assertEqual([result["orchestration"]["id"]], started)


if __name__ == "__main__":
    unittest.main()
