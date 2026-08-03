"""Progressive Skill discovery and next-round activation coverage (WB-334)."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime, skills_store  # noqa: E402
from agent.llm import Delta, ToolCallDelta  # noqa: E402
from agent.skill_discovery import (  # noqa: E402
    build_skill_candidates,
    clear_skill_candidates,
    set_skill_candidates,
    skill_view,
    skills_list,
)
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class SkillProgressiveDisclosureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_skills = settings.SKILLS_DIR
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate.db"
        settings.SKILLS_DIR = Path(self.tmp.name) / "skills"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        skills_store.set_owner(LOCAL_USER_ID)
        skills_store.install_catalog_skill(
            "web-access",
            "Web Access（浏览器自动化）",
            "联网取材测试",
            "SECRET_PROGRESSIVE_BODY：必须先抓取真实网页。",
            "1",
            files=[{"path": "references/guide.md", "content": "引用说明"}],
            tools=["web_fetch"],
        )

    def tearDown(self) -> None:
        clear_skill_candidates()
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.SKILLS_DIR = self.old_skills
        settings.WORKSPACE_ROOT = self.old_workspace
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None
        db._local = threading.local()

    def test_compact_index_omits_body_and_view_returns_release_trace(self) -> None:
        candidates = build_skill_candidates(["web-access"])
        self.assertEqual(["web-access"], [item["slug"] for item in candidates])
        set_skill_candidates(candidates)

        listing = skills_list.run({"query": "联网"}).text
        self.assertIn("web-access", listing)
        self.assertIn("项目候选", listing)
        self.assertNotIn("SECRET_PROGRESSIVE_BODY", listing)

        viewed = skill_view.run({"name": "web-access"})
        self.assertIn("SECRET_PROGRESSIVE_BODY", viewed.text)
        self.assertEqual("skill_view", viewed.trace[0]["tool"])
        self.assertEqual("web-access", viewed.trace[0]["slug"])
        self.assertTrue(viewed.trace[0]["release_id"])

    def test_disabled_and_tampered_catalog_skills_are_not_candidates(self) -> None:
        self.assertTrue(skills_store.set_disabled("web-access", True))
        self.assertEqual([], build_skill_candidates(["web-access"]))
        self.assertTrue(skills_store.set_disabled("web-access", False))

        package = skills_store.package_dir("web-access")
        self.assertIsNotNone(package)
        (package / skills_store.SKILL_MD).write_text("tampered", encoding="utf-8")
        self.assertEqual([], build_skill_candidates(["web-access"]))

    def test_non_project_candidate_loads_body_and_tools_only_in_next_round(self) -> None:
        project = db.create_project(
            owner_id=LOCAL_USER_ID, name="progressive", skills=[],
        )
        session = db.create_session(
            owner_id=LOCAL_USER_ID,
            title="progressive",
            kind="projexec",
            project_id=project.id,
        )
        captured: list[dict[str, object]] = []

        async def fake_stream(messages, **kwargs):
            captured.append({
                "system": str(messages[0]["content"]),
                "tools": {
                    item["function"]["name"] for item in kwargs.get("tools", [])
                    if item.get("function")
                },
                "messages": list(messages),
            })
            if not any(message.get("role") == "tool" for message in messages):
                yield Delta(
                    tool_calls=[ToolCallDelta(
                        index=0,
                        id="call-skill-view",
                        name="skill_view",
                        arguments=json.dumps({"name": "web-access"}),
                    )],
                    usage={"prompt_tokens": 10, "completion_tokens": 2},
                )
            else:
                yield Delta(content="已按技能执行。", usage={"prompt_tokens": 12, "completion_tokens": 3})

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def collect() -> list[str]:
            return [
                chunk async for chunk in runtime.run_chat(
                    session, db.get_user(LOCAL_USER_ID), "请联网取材",
                )
            ]

        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            payload = "".join(asyncio.run(collect()))

        self.assertEqual(2, len(captured))
        self.assertIn("web-access", captured[0]["system"])
        self.assertNotIn("SECRET_PROGRESSIVE_BODY", captured[0]["system"])
        self.assertIn("skill_view", captured[0]["tools"])
        self.assertNotIn("web_fetch", captured[0]["tools"])
        self.assertIn("web_fetch", captured[1]["tools"])
        self.assertIn(
            "SECRET_PROGRESSIVE_BODY",
            json.dumps(captured[1]["messages"], ensure_ascii=False),
        )
        self.assertIn("已按需加载技能", payload)

        run = db.list_runs(LOCAL_USER_ID, session_id=session.id)[0]
        self.assertEqual(["web-access"], run.permission_snapshot["skills"])
        self.assertEqual([], run.permission_snapshot["project_skill_candidates"])
        self.assertEqual("web-access", run.permission_snapshot["skill_releases"][0]["slug"])
        self.assertIn("web_fetch", run.permission_snapshot["tools"])
        self.assertIn("network.read", run.permission_snapshot["permissions"])
        context_keys = [item["key"] for item in run.permission_snapshot["context_layers"]]
        self.assertEqual(["system_core", "precedence"], context_keys[:2])
        self.assertIn("skill_candidates", context_keys)
        compliance = run.permission_snapshot["skill_compliance"]
        self.assertEqual(["web-access"], compliance["offered"])
        self.assertEqual(["web-access"], compliance["viewed_loaded"])
        self.assertEqual([], compliance["not_loaded"])
        usage = db.get_conn().execute(
            "SELECT event,COUNT(*) AS total FROM skill_usage_events WHERE run_id=? GROUP BY event",
            (run.id,),
        ).fetchall()
        totals = {row["event"]: int(row["total"]) for row in usage}
        self.assertEqual(1, totals.get("offered"))
        self.assertEqual(1, totals.get("loaded"))

    def test_project_bound_skill_is_loaded_before_first_model_call(self) -> None:
        project = db.create_project(
            owner_id=LOCAL_USER_ID, name="required", skills=["web-access"],
        )
        session = db.create_session(
            owner_id=LOCAL_USER_ID, title="required", kind="projexec", project_id=project.id,
        )
        captured: list[dict[str, object]] = []

        async def fake_stream(messages, **kwargs):
            captured.append({
                "system": str(messages[0]["content"]),
                "tools": {
                    item["function"]["name"] for item in kwargs.get("tools", [])
                    if item.get("function")
                },
            })
            yield Delta(content="已按项目规程执行。", usage={"prompt_tokens": 8, "completion_tokens": 2})

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def collect() -> list[str]:
            return [chunk async for chunk in runtime.run_chat(
                session, db.get_user(LOCAL_USER_ID), "执行项目任务",
            )]

        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            asyncio.run(collect())

        self.assertEqual(1, len(captured))
        self.assertIn("SECRET_PROGRESSIVE_BODY", captured[0]["system"])
        self.assertIn("web_fetch", captured[0]["tools"])
        self.assertNotIn("skill_view", captured[0]["tools"])
        run = db.list_runs(LOCAL_USER_ID, session_id=session.id)[0]
        self.assertEqual(["web-access"], run.permission_snapshot["required_project_skills"])
        compliance = run.permission_snapshot["skill_compliance"]
        self.assertEqual("passed", compliance["gate"])
        self.assertEqual(["web-access"], compliance["required_loaded"])

    def test_missing_project_skill_fails_before_model_call(self) -> None:
        project = db.create_project(
            owner_id=LOCAL_USER_ID, name="blocked", skills=["missing-required"],
        )
        session = db.create_session(
            owner_id=LOCAL_USER_ID, title="blocked", kind="projexec", project_id=project.id,
        )

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def collect() -> list[str]:
            return [chunk async for chunk in runtime.run_chat(
                session, db.get_user(LOCAL_USER_ID), "不要加载规程，直接执行",
            )]

        with (
            patch.object(runtime, "stream_chat") as stream_mock,
            patch.object(runtime, "resolve_model_config") as model_mock,
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            payload = "".join(asyncio.run(collect()))

        stream_mock.assert_not_called()
        model_mock.assert_not_called()
        self.assertIn("执行前阻断", payload)
        run = db.list_runs(LOCAL_USER_ID, session_id=session.id)[0]
        self.assertEqual("failed", run.status)
        self.assertEqual("required_skill_unavailable", run.error_code)
        self.assertEqual("blocked", run.permission_snapshot["skill_compliance"]["gate"])


if __name__ == "__main__":
    unittest.main()
