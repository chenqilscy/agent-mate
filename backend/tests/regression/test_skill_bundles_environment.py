"""Named Skill bundles and platform/environment/tool gates (WB-338)."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime, skill_bundles, skill_discovery, skills_store  # noqa: E402
from agent.llm import Delta  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


def manifest(
    slug: str,
    *,
    name: str = "",
    platforms: list[str] | None = None,
    environments: list[str] | None = None,
    requires_tools: list[str] | None = None,
) -> bytes:
    lines = [
        "---",
        f"name: {name or slug}",
        f"slug: {slug}",
        "description: bundle and environment regression",
    ]
    for key, values in (
        ("platforms", platforms),
        ("environments", environments),
        ("requires_tools", requires_tools),
    ):
        if values:
            lines.append(f"{key}: [{', '.join(values)}]")
    lines.extend(["---", "", "Follow the compatible workflow."])
    return "\n".join(lines).encode()


class SkillBundlesEnvironmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_skills = settings.SKILLS_DIR
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close()
        root = Path(self.tmp.name)
        settings.DB_PATH = root / "test.db"
        settings.SKILLS_DIR = root / "skills"
        settings.WORKSPACE_ROOT = root / "workspace"
        settings.WORKSPACE_ROOT.mkdir()
        db.init_db()
        skills_store.set_owner(LOCAL_USER_ID)
        skills_store.set_environment(["adhoc"])
        skills_store._invalidate_cache()

    def tearDown(self) -> None:
        skill_discovery.clear_skill_candidates()
        skills_store.set_owner(None)
        skills_store.set_environment(["adhoc"])
        skills_store._invalidate_cache()
        self._close()
        settings.DB_PATH = self.old_db
        settings.SKILLS_DIR = self.old_skills
        settings.WORKSPACE_ROOT = self.old_workspace
        self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()

    def test_bundle_crud_preserves_order_reports_missing_and_is_owner_scoped(self) -> None:
        skills_store.import_skill_file("alpha.md", manifest("alpha", name="Alpha"))
        skills_store.import_skill_file("beta.md", manifest("beta", name="Beta"))
        bundle = skill_bundles.create(
            LOCAL_USER_ID, "Release set", "cross-project reusable", ["beta", "missing", "alpha", "beta"],
        )
        self.assertEqual(["beta", "missing", "alpha"], bundle["skills"])

        first = skill_bundles.resolve(LOCAL_USER_ID, [bundle["id"]])
        second = skill_bundles.resolve(LOCAL_USER_ID, [bundle["id"]])
        self.assertEqual(["beta", "alpha"], first["skills"])
        self.assertEqual(first, second)
        self.assertEqual("missing", first["missing_skills"][0]["skill"])

        updated = skill_bundles.update(
            bundle["id"], LOCAL_USER_ID,
            name="Incident set", description="edited", skills=["alpha", "beta"],
        )
        self.assertEqual(["alpha", "beta"], updated["skills"])
        self.assertEqual(["alpha", "beta"], skill_bundles.resolve(LOCAL_USER_ID, [bundle["id"]])["skills"])
        self.assertIsNone(skill_bundles.get(bundle["id"], "owner-b"))
        self.assertEqual([bundle["id"]], skill_bundles.resolve("owner-b", [bundle["id"]])["missing_bundles"])
        self.assertTrue(skill_bundles.delete(bundle["id"], LOCAL_USER_ID))
        self.assertEqual([], skill_bundles.list_bundles(LOCAL_USER_ID))

    def test_platform_gate_filters_candidates_and_explicit_view_explains_reason(self) -> None:
        skills_store.import_skill_file(
            "platform.md", manifest("platform-only", platforms=["windows"]),
        )
        with patch.object(skills_store.sys, "platform", "win32"):
            self.assertIn(
                "platform-only",
                {item["slug"] for item in skill_discovery.build_skill_candidates([])},
            )
        with patch.object(skills_store.sys, "platform", "linux"):
            candidates = skill_discovery.build_skill_candidates([])
            self.assertNotIn("platform-only", {item["slug"] for item in candidates})
            skill_discovery.set_skill_candidates(candidates)
            result = skill_discovery.skill_view.run({"name": "platform-only"})
            self.assertIn("当前环境不适用", result.text)
            self.assertIn("windows", result.text)

    def test_environment_and_tool_contract_gate_apply_to_candidate_and_load(self) -> None:
        skills_store.import_skill_file(
            "server.md",
            manifest(
                "server-project-only",
                environments=["server-project"],
                requires_tools=["read_file"],
            ),
        )
        skills_store.set_environment(["project"])
        self.assertIn("需要环境 server-project", skills_store.incompatibility_reason("server-project-only"))
        self.assertEqual([], skill_discovery.build_skill_candidates([]))

        skills_store.set_environment(["project", "server-project"])
        self.assertEqual("", skills_store.incompatibility_reason("server-project-only"))
        self.assertIn(
            "server-project-only",
            {item["slug"] for item in skill_discovery.build_skill_candidates([])},
        )

        skills_store.import_skill_file(
            "missing-tool.md",
            manifest("missing-tool", requires_tools=["definitely_missing_tool"]),
        )
        reason = skills_store.incompatibility_reason("missing-tool")
        self.assertIn("缺少所需工具契约", reason)
        candidates = skill_discovery.build_skill_candidates([])
        self.assertNotIn("missing-tool", {item["slug"] for item in candidates})

    def test_agentmate_catalog_snapshot_persists_compatibility_frontmatter(self) -> None:
        installed = skills_store.install_catalog_skill(
            "catalog-gated", "Catalog gated", "catalog environment gate",
            "Use read_file only in a project.", tools=["read_file"],
            platforms=["windows", "linux"],
            environments=["project"],
            requires_tools=["read_file"],
        )
        detail = skills_store.detail(installed["skill"]["key"])
        self.assertEqual(["windows", "linux"], detail["platforms"])
        self.assertEqual(["project"], detail["environments"])
        self.assertEqual(["read_file"], detail["requires_tools"])

    def test_runtime_invokes_bundle_in_stable_order_and_snapshots_missing_items(self) -> None:
        skills_store.import_skill_file("alpha.md", manifest("alpha", name="Alpha"))
        skills_store.import_skill_file("beta.md", manifest("beta", name="Beta"))
        bundle = skill_bundles.create(
            LOCAL_USER_ID, "Reusable bundle", "", ["beta", "missing", "alpha"],
        )
        session = db.create_session(owner_id=LOCAL_USER_ID, title="bundle runtime")
        captured: list[str] = []

        async def fake_stream(messages, **_kwargs):
            captured.append(str(messages[0]["content"]))
            yield Delta(content="done", usage={"prompt_tokens": 2, "completion_tokens": 1})

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def collect() -> str:
            return "".join([
                chunk async for chunk in runtime.run_chat(
                    session,
                    db.get_user(LOCAL_USER_ID),
                    "use the reusable bundle",
                    bundle_ids=[bundle["id"]],
                )
            ])

        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
        ):
            payload = asyncio.run(collect())

        self.assertEqual(1, len(captured))
        self.assertIn("Reusable bundle", payload)
        self.assertIn("Reusable bundle:missing", payload)
        run = db.list_runs(LOCAL_USER_ID, session_id=session.id)[0]
        self.assertEqual(["beta", "alpha"], run.permission_snapshot["skills"])
        self.assertEqual("Reusable bundle", run.permission_snapshot["skill_bundles"][0]["name"])
        self.assertEqual("missing", run.permission_snapshot["missing_bundle_skills"][0]["skill"])


if __name__ == "__main__":
    unittest.main()
