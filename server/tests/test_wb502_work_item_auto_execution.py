"""WB-502 gate-driven, one-shot WorkItem auto execution policy."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import business_store  # noqa: E402
import db  # noqa: E402
import work_item_auto_scheduler as scheduler  # noqa: E402
from config import settings  # noqa: E402
from routers.work_items import (  # noqa: E402
    AcceptBody,
    ExecutionPolicyBody,
    accept_item,
    set_execution_policy,
)


CORE = ["run_events_v1", "llm.chat", "agent.tools"]


class WorkItemAutoExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-502", password="password123")
        self.project = db.create_project(name="auto-work", owner_id=self.owner.id)
        self.item = db.create_work_item(
            project_id=self.project.id,
            title="自动交付任务",
            description="生成 result.md",
            assignee=self.owner.id,
        )
        self.device_id = "device-owner-502"
        self._device(capabilities=CORE, last_seen=time.time())

    def tearDown(self) -> None:
        self._close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _device(self, *, capabilities: list[str], last_seen: float) -> None:
        now = time.time()
        db.get_conn().execute(
            "INSERT OR REPLACE INTO agent_devices "
            "(id,owner_id,name,public_key,protocol_version,app_version,platform,arch,capabilities,"
            "status,created_at,updated_at,authenticated_at,last_seen_at,revoked_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,?,?,0)",
            (
                self.device_id, self.owner.id, "Auto Agent", "public-key-502", 1, "1.0",
                "test", "x64", json.dumps({
                    "capabilities": capabilities,
                    "max_parallel_runs": 1,
                    "max_resident_runs": 4,
                }), now, now, now, last_seen,
            ),
        )
        db.get_conn().commit()

    def _policy(self, **overrides) -> dict:
        values = {
            "mode": "auto",
            "routing_mode": "any_compatible",
            "target_device_id": "",
            "required_capabilities": CORE,
            "timeout_sec": 300,
            "max_attempts": 2,
            "retry_backoff_sec": 1,
            "max_total_tokens": 0,
            "notify_policy": "failure,recovery",
            "preauthorized_permissions": ["workspace.write"],
        }
        values.update(overrides)
        policy, _changed = scheduler.configure_policy(
            work_item=db.get_work_item(self.item["id"]),
            execution_owner_id=self.owner.id,
            values=values,
        )
        return policy

    def _runs(self) -> list[dict]:
        return business_store.list_scoped(
            "business_runs",
            account_id=self.owner.id,
            project_id=self.project.id,
            parent=("work_item_id", self.item["id"]),
            limit=20,
        )[0]

    def test_same_policy_version_queues_exactly_one_run_and_waits_for_acceptance(self) -> None:
        policy = self._policy()
        first = scheduler.trigger_one(self.item["id"])
        replay = scheduler.trigger_one(self.item["id"])
        self.assertEqual("queued", first["state"])
        self.assertEqual(first["last_run_id"], replay["last_run_id"])
        self.assertEqual(1, len(self._runs()))
        unchanged, changed = scheduler.configure_policy(
            work_item=db.get_work_item(self.item["id"]),
            execution_owner_id=self.owner.id,
            values={
                key: policy[key] for key in (
                    "mode", "routing_mode", "target_device_id", "required_capabilities",
                    "model_ref", "timeout_sec", "max_attempts", "retry_backoff_sec",
                    "max_total_tokens", "notify_policy", "preauthorized_permissions",
                )
            },
        )
        self.assertFalse(changed)
        self.assertEqual(policy["version"], unchanged["version"])

        run = self._runs()[0]
        business_store.create_record(
            "business_assets",
            entity_type="asset",
            actor_id=self.owner.id,
            owner_id=self.owner.id,
            project_id=self.project.id,
            fields={
                "session_id": run["session_id"], "run_id": run["id"], "kind": "artifact",
                "name": "result.md", "size": 12, "sha256": "a" * 64,
                "storage_state": "committed", "object_ref": "object://sha256/result",
                "validation_status": "verified", "validation": {"sha256": "a" * 64},
            },
        )
        db.get_conn().execute(
            "UPDATE business_runs SET status='completed',ended_at=?,updated_at=? WHERE id=?",
            (time.time(), time.time(), run["id"]),
        )
        db.get_conn().execute(
            "UPDATE work_items SET status='review' WHERE id=?", (self.item["id"],),
        )
        db.get_conn().commit()
        terminal = scheduler.trigger_one(self.item["id"])
        self.assertEqual("awaiting_acceptance", terminal["state"])
        self.assertEqual("review", db.get_work_item(self.item["id"])["status"])
        self.assertEqual(1, len(self._runs()))

        accepted = accept_item(
            self.project.id, self.item["id"],
            AcceptBody(run_id=run["id"], artifact_count=1), self.owner,
        )
        self.assertEqual("done", accepted["status"])
        self.assertTrue(accepted["delivery_accepted"])
        self.assertEqual("accepted", accepted["execution_policy"]["state"])

    def test_policy_api_preserves_timeout_retry_and_budget_fields(self) -> None:
        response = set_execution_policy(
            self.project.id,
            self.item["id"],
            ExecutionPolicyBody(
                mode="auto",
                routing_mode="any_compatible",
                required_capabilities=CORE,
                model_ref="provider/model-502",
                timeout_sec=77,
                max_attempts=4,
                retry_backoff_sec=19,
                max_total_tokens=4321,
                notify_policy="failure",
                preauthorized_permissions=["workspace.write"],
            ),
            self.owner,
        )
        policy = response["policy"]
        self.assertEqual("provider/model-502", policy["model_ref"])
        self.assertEqual(77, policy["timeout_sec"])
        self.assertEqual(4, policy["max_attempts"])
        self.assertEqual(19, policy["retry_backoff_sec"])
        self.assertEqual(4321, policy["max_total_tokens"])

    def test_manual_done_is_not_reported_as_delivery_acceptance(self) -> None:
        self._policy()
        db.update_work_item(self.item["id"], status="done")
        policy = scheduler.trigger_one(self.item["id"])
        self.assertEqual("completed_without_acceptance", policy["state"])
        self.assertEqual("completed_without_acceptance", policy["blocker_code"])
        self.assertIsNone(db.get_work_item_acceptance(self.item["id"]))

    def test_dependency_sprint_device_capability_and_permission_gates_are_observable(self) -> None:
        dependency = db.create_work_item(project_id=self.project.id, title="前置任务")
        sprint = db.create_sprint(
            project_id=self.project.id, name="Sprint 502", goal="", start_date="2026-08-01",
            end_date="2026-08-31", status="planned",
        )
        db.update_work_item(
            self.item["id"], dependency_ids=[dependency["id"]], sprint_id=sprint["id"],
        )
        self._policy()
        self.assertEqual("dependency_incomplete", scheduler.trigger_one(self.item["id"])["blocker_code"])

        db.update_work_item(dependency["id"], status="done")
        self.assertEqual("sprint_inactive", scheduler.trigger_one(self.item["id"])["blocker_code"])
        db.update_sprint(sprint["id"], status="active")

        self._device(capabilities=CORE, last_seen=time.time() - 600)
        self.assertEqual("device_offline", scheduler.trigger_one(self.item["id"])["blocker_code"])
        self._device(capabilities=["run_events_v1"], last_seen=time.time())
        self.assertEqual("capability_mismatch", scheduler.trigger_one(self.item["id"])["blocker_code"])

        self._device(capabilities=CORE, last_seen=time.time())
        self._policy(preauthorized_permissions=[])
        missing = scheduler.trigger_one(self.item["id"])
        self.assertEqual("permission_missing", missing["blocker_code"])
        self.assertEqual([], self._runs())

        self._policy(preauthorized_permissions=["workspace.write", "process.execute"])
        risky = scheduler.trigger_one(self.item["id"])
        self.assertEqual("high_risk_permission", risky["blocker_code"])
        self.assertEqual([], self._runs())

    def test_failed_attempt_creates_retry_chain_without_duplicate_active_run(self) -> None:
        self._policy(max_attempts=2, retry_backoff_sec=1)
        first_policy = scheduler.trigger_one(self.item["id"])
        first_run_id = first_policy["last_run_id"]
        ended = time.time() - 10
        db.get_conn().execute(
            "UPDATE business_runs SET status='failed',error_code='tool_failed',ended_at=?,updated_at=? WHERE id=?",
            (ended, ended, first_run_id),
        )
        db.get_conn().execute("UPDATE work_items SET status='paused' WHERE id=?", (self.item["id"],))
        db.get_conn().commit()

        retried = scheduler.trigger_one(self.item["id"], force_retry=True)
        self.assertEqual("queued", retried["state"])
        self.assertEqual(2, retried["last_attempt"])
        runs = self._runs()
        self.assertEqual(2, len(runs))
        newest = next(run for run in runs if run["id"] == retried["last_run_id"])
        self.assertEqual(first_run_id, newest["retry_of"])
        replay = scheduler.trigger_one(self.item["id"], force_retry=True)
        self.assertEqual(retried["last_run_id"], replay["last_run_id"])
        self.assertEqual(2, len(self._runs()))


if __name__ == "__main__":
    unittest.main()
