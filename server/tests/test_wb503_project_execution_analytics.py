"""WB-503 project execution analytics metric and permission contracts."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import business_store  # noqa: E402
import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from project_execution_analytics import build_project_execution_analytics  # noqa: E402
from routers.project_analytics import execution_analytics  # noqa: E402


class ProjectExecutionAnalyticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-503", password="password123")
        self.viewer = db.create_account(name="viewer-503", password="password123")
        self.outsider = db.create_account(name="outsider-503", password="password123")
        self.project = db.create_project(name="analytics", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)
        self.item = db.create_work_item(project_id=self.project.id, title="首次交付", assignee=self.owner.id)
        self._seed()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    def _seed(self) -> None:
        session, _ = business_store.create_record(
            "business_sessions", entity_type="session", actor_id=self.owner.id,
            owner_id=self.owner.id, project_id=self.project.id,
            fields={"title": "analytics", "kind": "project", "status": "idle"},
            record_id="session-503",
        )
        now = time.time()
        common = {
            "session_id": session["id"], "work_item_id": self.item["id"], "mode": "exec",
            "workspace": f"project:{self.project.id}", "model_ref": "provider/model",
        }
        completed, _ = business_store.create_record(
            "business_runs", entity_type="run", actor_id=self.owner.id,
            owner_id=self.owner.id, project_id=self.project.id,
            fields={**common, "status": "completed", "started_at": now - 80, "ended_at": now - 50,
                    "prompt_tokens": 100, "cached_prompt_tokens": 20, "completion_tokens": 40,
                    "estimated_cost": 0.25, "cost_currency": "USD"},
            record_id="run-completed-503",
        )
        failed, _ = business_store.create_record(
            "business_runs", entity_type="run", actor_id=self.owner.id,
            owner_id=self.owner.id, project_id=self.project.id,
            fields={**common, "status": "failed", "retry_of": completed["id"],
                    "started_at": now - 40, "ended_at": now - 20,
                    "prompt_tokens": 30, "completion_tokens": 10,
                    "error_code": "tool_failed", "error_message": "redacted test error"},
            record_id="run-failed-503",
        )
        queued, _ = business_store.create_record(
            "business_runs", entity_type="run", actor_id=self.owner.id,
            owner_id=self.owner.id, project_id=self.project.id,
            fields={**common, "status": "queued", "target_device_id": "device-503",
                    "required_capabilities": ["run_events_v1", "llm.chat", "agent.tools"]},
            record_id="run-queued-503",
        )
        conn = db.get_conn()
        conn.execute(
            "UPDATE business_runs SET created_at=? WHERE id=?", (now - 100, completed["id"]),
        )
        conn.execute(
            "UPDATE business_runs SET created_at=? WHERE id=?", (now - 60, failed["id"]),
        )
        conn.execute(
            "UPDATE business_runs SET created_at=? WHERE id=?", (now - 10, queued["id"]),
        )
        conn.execute(
            "INSERT INTO agent_devices "
            "(id,owner_id,name,public_key,status,protocol_version,capabilities,created_at,updated_at,authenticated_at,last_seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("device-503", self.owner.id, "离线分析节点", "pk-503", "active", 1,
             '{"capabilities":["run_events_v1","llm.chat","agent.tools"],"max_parallel_runs":2}',
             now, now, now, now - 999),
        )
        conn.commit()
        asset, _ = business_store.create_record(
            "business_assets", entity_type="asset", actor_id=self.owner.id,
            owner_id=self.owner.id, project_id=self.project.id,
            fields={"session_id": session["id"], "run_id": completed["id"], "name": "report.md",
                    "storage_state": "committed", "validation_status": "verified",
                    "acceptance_status": "accepted", "sha256": "a" * 64},
            record_id="asset-503",
        )
        self.assertEqual("asset-503", asset["id"])
        db.update_work_item(self.item["id"], status="review")
        db.accept_work_item_delivery(
            project_id=self.project.id, work_item_id=self.item["id"], run_id=completed["id"],
            artifact_count=1, actor_id=self.owner.id, actor_name=self.owner.name,
        )

    def test_metrics_are_recomputable_and_keep_unknown_cost_separate(self) -> None:
        result = build_project_execution_analytics(self.project.id, days=7, timezone_name="UTC")
        self.assertEqual("project-execution-v1", result["metric_version"])
        self.assertEqual(3, result["summary"]["runs"])
        self.assertEqual(1, result["summary"]["completed"])
        self.assertEqual(1, result["summary"]["failed"])
        self.assertEqual(0.5, result["summary"]["success_rate"])
        self.assertEqual(1, result["summary"]["retry_runs"])
        self.assertEqual(0.25, result["summary"]["estimated_cost"]["USD"])
        self.assertEqual(2, result["summary"]["unpriced_runs"])
        self.assertEqual(1.0, result["delivery"]["artifact_verification_rate"])
        self.assertEqual(1.0, result["delivery"]["first_pass_acceptance_rate"])
        self.assertEqual("device_offline", result["queue_blockers"][0]["reason"])
        self.assertEqual("tool_failed", result["failures"][0]["error_code"])
        self.assertNotIn("error_message", result["slow_runs"][0])
        self.assertNotIn("request_snapshot", str(result))

    def test_viewer_can_read_project_but_outsider_cannot(self) -> None:
        viewer_result = execution_analytics(self.project.id, 7, "Asia/Shanghai", self.viewer)
        self.assertEqual(self.project.id, viewer_result["project_id"])
        with self.assertRaises(HTTPException) as rejected:
            execution_analytics(self.project.id, 7, "UTC", self.outsider)
        self.assertEqual(404, rejected.exception.status_code)

    def test_window_and_timezone_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            build_project_execution_analytics(self.project.id, days=8)
        with self.assertRaises(ValueError):
            build_project_execution_analytics(self.project.id, timezone_name="Not/A-Timezone")
