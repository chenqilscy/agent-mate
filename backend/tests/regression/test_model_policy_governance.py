"""WB-386 model allowlist, budget, provider-health and Server-policy governance."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import tempfile
import time
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from agent import runtime  # noqa: E402
from config import settings  # noqa: E402
from routers import models as models_router  # noqa: E402
import server_client  # noqa: E402
import server_sync  # noqa: E402
from storage import db, model_governance, provider_seed  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ModelPolicyGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self.old_host = settings.HOST
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        settings.HOST = "127.0.0.1"
        db.init_db()
        set_current_user_id(LOCAL_USER_ID)
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="model policy")

    def tearDown(self) -> None:
        set_current_user_id(None)
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        settings.HOST = self.old_host
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def test_allowlist_and_recent_unhealthy_provider_select_safe_fallback(self) -> None:
        primary = "@deepseek:deepseek-v4-flash"
        fallback = "@openai:gpt-4o-mini"
        db.set_provider_key(LOCAL_USER_ID, "deepseek", "deepseek-secret")
        db.set_provider_key(LOCAL_USER_ID, "openai", "openai-secret")
        db.set_default_model(LOCAL_USER_ID, primary)
        db.set_user_model_policy(LOCAL_USER_ID, model_governance.normalize_policy({
            "allowlist": [primary, fallback],
            "fallback_chain": [fallback],
            "provider_health_ttl_seconds": 900,
        }))
        now = time.time()
        db.set_provider_health(
            LOCAL_USER_ID, "deepseek", status="unhealthy", checked_at=now,
            error_code="http_503",
            endpoint_hash=model_governance.endpoint_hash(
                provider_seed.PROVIDERS_BY_ID["deepseek"]["base_url"],
            ),
        )

        decision = model_governance.policy_decision(LOCAL_USER_ID, primary, now=now)
        self.assertTrue(decision["allowed"])
        self.assertEqual(fallback, decision["selected_model_ref"])
        self.assertEqual(primary, decision["fallback_from"])
        self.assertEqual("provider_unhealthy_fallback", decision["selection_reason"])
        self.assertNotIn("secret", repr(decision).lower())

        blocked = model_governance.policy_decision(
            LOCAL_USER_ID, "@qwen:qwen-plus", now=now,
        )
        self.assertFalse(blocked["allowed"])
        self.assertIn("允许列表", blocked["error"])

    def test_hard_budget_reports_remaining_capacity_and_then_denies(self) -> None:
        model_ref = "@deepseek:deepseek-v4-flash"
        db.set_provider_key(LOCAL_USER_ID, "deepseek", "key")
        db.set_default_model(LOCAL_USER_ID, model_ref)
        db.set_user_model_policy(LOCAL_USER_ID, model_governance.normalize_policy({
            "allowlist": [model_ref], "daily_soft_tokens": 80,
            "daily_hard_tokens": 100, "monthly_hard_tokens": 1000,
        }))
        run, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID,
            project_id=None, mode="exec",
        )
        db.update_run_runtime(run.id, prompt_tokens=60, completion_tokens=30)

        decision = model_governance.policy_decision(LOCAL_USER_ID, model_ref)
        self.assertTrue(decision["allowed"])
        self.assertEqual(10, decision["hard_remaining_tokens"])
        self.assertTrue(any("软预算" in warning for warning in decision["warnings"]))

        db.update_run_runtime(run.id, prompt_tokens=60, completion_tokens=40)
        denied = model_governance.policy_decision(LOCAL_USER_ID, model_ref)
        self.assertFalse(denied["allowed"])
        self.assertIn("硬预算", denied["error"])

    def test_runtime_enforces_policy_before_resolving_or_calling_model(self) -> None:
        db.set_user_model_policy(LOCAL_USER_ID, model_governance.normalize_policy({
            "allowlist": ["@deepseek:deepseek-v4-flash"],
        }))

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def collect() -> list[str]:
            return [event async for event in runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "blocked",
                model="@openai:gpt-4o-mini",
            )]

        with (
            patch.object(runtime, "resolve_model_config") as resolver,
            patch.object(runtime, "workspace_root", return_value=settings.WORKSPACE_ROOT / "default"),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            events = asyncio.run(collect())

        resolver.assert_not_called()
        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual("failed", run.status)
        self.assertIn("允许列表", run.error_message)
        self.assertIn("error", "".join(events))

    def test_organization_policy_is_inherited_from_server_project(self) -> None:
        db.mirror_server_project(
            id="project-1", name="server project", owner_id=LOCAL_USER_ID,
            org_id="org-1",
        )
        db.replace_server_org_model_policies([{
            "org_id": "org-1", "revision": 7, "updated_at": time.time(),
            "policy": {"allowlist": ["@deepseek:deepseek-v4-flash"]},
        }])
        decision = model_governance.policy_decision(
            LOCAL_USER_ID, "@openai:gpt-4o-mini", project_id="project-1",
        )
        self.assertFalse(decision["allowed"])
        self.assertIn("organization", decision["error"])
        payload = model_governance.governance_payload(
            LOCAL_USER_ID, project_id="project-1",
        )
        self.assertEqual("org-1", payload["organization"]["org_id"])
        self.assertEqual(7, payload["organization"]["revision"])

    def test_shared_backend_rejects_local_endpoint_but_local_first_allows_it(self) -> None:
        self.assertEqual(
            "http://127.0.0.1:11434/v1",
            model_governance.validate_endpoint_url("http://127.0.0.1:11434/v1"),
        )
        with patch.object(settings, "HOST", "0.0.0.0"):
            with self.assertRaisesRegex(ValueError, "共享后端"):
                model_governance.validate_endpoint_url("http://127.0.0.1:11434/v1")
            with self.assertRaisesRegex(HTTPException, "共享后端"):
                models_router.set_provider_config(
                    "deepseek", models_router.ProviderConfigIn(
                        base_url="http://localhost:11434/v1", chat_path="/chat/completions",
                    ),
                )

    def test_model_catalog_exposes_health_and_rotation_metadata_without_keys(self) -> None:
        db.set_provider_key(LOCAL_USER_ID, "deepseek", "must-never-leak")
        db.set_provider_health(
            LOCAL_USER_ID, "deepseek", status="unhealthy", checked_at=time.time(),
            error_code="timeout", endpoint_hash="abc",
        )
        payload = models_router.list_models()
        deepseek = next(item for item in payload["providers"] if item["id"] == "deepseek")
        self.assertTrue(deepseek["credential_updated_at"] > 0)
        self.assertEqual("unhealthy", deepseek["health"]["status"])
        self.assertEqual("timeout", deepseek["health"]["error_code"])
        self.assertNotIn("must-never-leak", repr(payload))

    def test_sync_persists_project_org_and_non_secret_policy(self) -> None:
        remote_project = {
            "id": "project-sync", "name": "synced", "owner_id": LOCAL_USER_ID,
            "org_id": "org-sync", "instruction": "", "connectors": [],
            "experts": [], "skills": [], "knowledge_ids": [],
        }
        remote_policy = {
            "org_id": "org-sync", "revision": 3, "updated_at": time.time(),
            "policy": {"allowlist": ["@openai:gpt-4o-mini"]},
        }
        with (
            patch.object(server_client, "list_projects", return_value=[remote_project]),
            patch.object(server_client, "list_org_model_policies", return_value=[remote_policy]),
            patch.object(server_client, "list_project_members", return_value=[]),
        ):
            result = server_sync.pull("unmapped-test-token")
        self.assertEqual(1, result["synced"])
        self.assertEqual(1, result["model_policies"])
        self.assertEqual("org-sync", db.get_project("project-sync").org_id)
        stored = db.get_server_org_model_policy("org-sync")
        self.assertEqual(3, stored["revision"])
        self.assertNotIn("key", repr(stored).lower())


if __name__ == "__main__":
    unittest.main()
