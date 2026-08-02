"""Run model snapshot, estimated-cost and owner budget governance (WB-346)."""
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

from agent import runtime  # noqa: E402
from agent.llm import Delta  # noqa: E402
from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import me as me_router, models as models_router  # noqa: E402
from storage import db, model_governance  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ModelCostGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="model governance")

    def tearDown(self) -> None:
        set_current_user_id(None)
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

    @staticmethod
    def _set_price(owner_id: str, ref: str, input_cost: float, output_cost: float, currency: str) -> None:
        db.set_model_meta(
            owner_id, ref, capabilities=["text", "tools"], input_cost=input_cost,
            input_cost_cached=None, output_cost=output_cost, context_window=128_000,
            currency=currency, note="test price",
        )

    def _priced_run(self, ref: str, model_id: str, prompt: int, completion: int):
        run, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="exec", workspace="default",
        )
        run = db.set_run_model_snapshot(
            run.id, model_ref=ref, model_id=model_id,
            snapshot=model_governance.build_run_snapshot(LOCAL_USER_ID, ref, model_id),
        )
        return db.update_run_runtime(run.id, prompt_tokens=prompt, completion_tokens=completion)

    def test_price_snapshot_is_immutable_and_retry_copies_it(self) -> None:
        self._set_price(LOCAL_USER_ID, "priced", 2, 4, "USD")
        run = self._priced_run("priced", "model-v1", 1_000_000, 500_000)
        self.assertEqual(4.0, run.estimated_cost)
        self.assertEqual("USD", run.cost_currency)
        self.assertEqual(2, run.model_snapshot["pricing"]["input_per_million"])

        self._set_price(LOCAL_USER_ID, "priced", 20, 40, "USD")
        historical = db.update_run_runtime(run.id, prompt_tokens=1_000_000, completion_tokens=500_000)
        fresh = self._priced_run("priced", "model-v1", 1_000_000, 500_000)
        self.assertEqual(4.0, historical.estimated_cost)
        self.assertEqual(40.0, fresh.estimated_cost)
        with self.assertRaisesRegex(ValueError, "immutable"):
            db.set_run_model_snapshot(
                run.id, model_ref="other", model_id="model-v2", snapshot={},
            )

        db.set_run_status(run.id, "failed", error_code="test", error_message="test")
        retry, created = db.create_retry_run(run.id, LOCAL_USER_ID, "retry-priced")
        self.assertTrue(created)
        self.assertEqual(run.model_snapshot, retry.model_snapshot)
        self.assertEqual(run.model_id, retry.model_id)

    def test_month_summary_separates_currencies_unpriced_and_owners(self) -> None:
        self._set_price(LOCAL_USER_ID, "usd", 1, 1, "USD")
        self._set_price(LOCAL_USER_ID, "cny", 2, 2, "CNY")
        self._priced_run("usd", "model-usd", 1000, 1000)
        self._priced_run("cny", "model-cny", 1000, 0)

        unpriced, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None, mode="exec",
        )
        db.set_run_model_snapshot(
            unpriced.id, model_ref="unknown", model_id="model-unknown",
            snapshot=model_governance.build_run_snapshot(LOCAL_USER_ID, "unknown", "model-unknown"),
        )
        db.update_run_runtime(unpriced.id, prompt_tokens=10)
        unresolved, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None, mode="exec",
        )
        db.update_run_runtime(unresolved.id, prompt_tokens=10)

        other = db.create_user(name="other-cost-owner", password="1111")
        other_session = db.create_session(owner_id=other.id, title="other")
        other_run, _ = db.create_run(
            session_id=other_session.id, owner_id=other.id, project_id=None, mode="exec",
        )
        db.update_run_runtime(other_run.id, prompt_tokens=999_999)

        summary = db.get_model_governance_summary(LOCAL_USER_ID)
        self.assertEqual(4, summary["runs"])
        self.assertEqual(1, summary["unpriced_runs"])
        self.assertEqual(1, summary["unresolved_runs"])
        self.assertEqual(["CNY", "USD"], [item["currency"] for item in summary["costs"]])
        self.assertEqual(3020, summary["total_tokens"])

    def test_governance_and_me_follow_owner_database_configuration(self) -> None:
        set_current_user_id(LOCAL_USER_ID)
        db.set_provider_key(LOCAL_USER_ID, "weknora", "knowledge-only")
        with patch.object(settings, "LLM_API_KEY", ""):
            self.assertFalse(model_governance.account_has_model_configuration(LOCAL_USER_ID))
        db.set_provider_key(LOCAL_USER_ID, "deepseek", "secret-never-returned")
        db.set_default_model(LOCAL_USER_ID, "@deepseek:deepseek-chat")
        response = models_router.set_model_governance(
            models_router.ModelGovernanceIn(default_run_token_budget=12_345)
        )
        self.assertEqual(12_345, response["policy"]["default_run_token_budget"])
        self.assertEqual(response["policy"], models_router.get_model_governance()["policy"])
        me = me_router.get_me()
        self.assertTrue(me["llm_configured"])
        self.assertEqual("@deepseek:deepseek-chat", me["model"])
        self.assertNotIn("secret", str(me).lower())

    def test_account_default_budget_applies_and_explicit_budget_wins(self) -> None:
        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def fifteen_tokens(_messages, **_kwargs):
            yield Delta(content="partial", usage={"prompt_tokens": 10, "completion_tokens": 5})

        async def collect(session, **kwargs):
            return [chunk async for chunk in runtime.run_chat(
                session, db.get_user(LOCAL_USER_ID), "budget", **kwargs,
            )]

        db.set_model_default_run_token_budget(LOCAL_USER_ID, 5)
        with (
            patch.object(runtime, "stream_chat", side_effect=fifteen_tokens),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=settings.WORKSPACE_ROOT / "default"),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            asyncio.run(collect(self.session))
            explicit_session = db.create_session(owner_id=LOCAL_USER_ID, title="explicit")
            asyncio.run(collect(explicit_session, max_total_tokens=100_000))

        default_run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        explicit_run = db.list_runs(LOCAL_USER_ID, session_id=explicit_session.id)[0]
        self.assertEqual("token_budget_exceeded", default_run.error_code)
        self.assertEqual("account_default", default_run.permission_snapshot["token_budget_source"])
        self.assertEqual("completed", explicit_run.status)
        self.assertEqual("explicit", explicit_run.permission_snapshot["token_budget_source"])

    def test_cached_prompt_tokens_use_snapshot_cached_rate(self) -> None:
        db.set_model_meta(
            LOCAL_USER_ID, "cached", capabilities=["text"], input_cost=10,
            input_cost_cached=2, output_cost=20, context_window=128_000,
            currency="USD", note="cached test",
        )
        run, _ = db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID,
            project_id=None, mode="exec",
        )
        db.set_run_model_snapshot(
            run.id, model_ref="cached", model_id="cached-v1",
            snapshot=model_governance.build_run_snapshot(
                LOCAL_USER_ID, "cached", "cached-v1",
            ),
        )
        priced = db.update_run_runtime(
            run.id, prompt_tokens=1_000_000, cached_prompt_tokens=750_000,
            completion_tokens=100_000,
        )
        self.assertEqual(750_000, priced.cached_prompt_tokens)
        self.assertEqual(6.0, priced.estimated_cost)


if __name__ == "__main__":
    unittest.main()
