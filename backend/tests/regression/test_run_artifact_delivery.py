"""Run/Artifact delivery-kernel regression coverage (WB-242)."""
from __future__ import annotations

import hashlib
import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from agent import runtime  # noqa: E402
from agent.llm import Delta, ToolCallDelta  # noqa: E402
from config import settings  # noqa: E402
from routers import runs as runs_router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class RunArtifactDeliveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="delivery test")

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

    def _run(self, **kwargs):
        return db.create_run(
            session_id=self.session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="exec", workspace="default", **kwargs,
        )

    def _artifact(self, run_id: str, content: bytes = b"deliverable"):
        path = settings.WORKSPACE_ROOT / "default" / "report.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return db.upsert_artifact(
            run_id=run_id, path="report.txt", full_path=path, source_tool="write_file",
        )

    def test_idempotency_reuses_one_run_without_duplicate_rows(self) -> None:
        first, created = self._run(idempotency_key="request-1")
        replay, replay_created = self._run(idempotency_key="request-1")
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(first.id, replay.id)
        self.assertEqual(1, len(db.list_runs(LOCAL_USER_ID)))

    def test_lifecycle_rejects_illegal_transition_and_persists_metrics(self) -> None:
        run, _ = self._run()
        with self.assertRaisesRegex(ValueError, "invalid run transition"):
            db.set_run_status(run.id, "accepted")
        db.update_run_runtime(run.id, prompt_tokens=12, completion_tokens=7, tool_calls=2)
        completed = db.set_run_status(run.id, "completed")
        self.assertEqual("completed", completed.status)
        self.assertEqual((12, 7, 2), (completed.prompt_tokens, completed.completion_tokens, completed.tool_calls))

    def test_artifact_manifest_hash_upserts_and_accepts_run(self) -> None:
        run, _ = self._run()
        artifact = self._artifact(run.id)
        self.assertEqual(hashlib.sha256(b"deliverable").hexdigest(), artifact.sha256)
        self.assertEqual(11, artifact.size)
        updated = self._artifact(run.id, b"revised")
        self.assertEqual(artifact.id, updated.id)
        self.assertEqual(1, len(db.list_artifacts(run.id)))
        db.set_run_status(run.id, "completed")
        reviewed = db.review_artifact(updated.id, "accepted", LOCAL_USER_ID)
        self.assertEqual("accepted", reviewed.acceptance_status)
        self.assertEqual("accepted", db.get_run(run.id).status)

    def test_artifact_primary_and_display_order_are_authoritative(self) -> None:
        run, _ = self._run()
        root = settings.WORKSPACE_ROOT / "default"
        root.mkdir(parents=True, exist_ok=True)
        first_path = root / "main.md"
        second_path = root / "appendix.md"
        first_path.write_text("main", encoding="utf-8")
        second_path.write_text("appendix", encoding="utf-8")
        first = db.upsert_artifact(
            run_id=run.id, path="main.md", full_path=first_path, source_tool="write_file",
        )
        second = db.upsert_artifact(
            run_id=run.id, path="appendix.md", full_path=second_path, source_tool="write_file",
        )
        self.assertTrue(first.is_primary)
        self.assertFalse(second.is_primary)
        self.assertEqual([0, 1], [item.display_order for item in db.list_artifacts(run.id)])

        first_path.write_text("main revised", encoding="utf-8")
        updated = db.upsert_artifact(
            run_id=run.id, path="main.md", full_path=first_path, source_tool="write_file",
        )
        self.assertEqual(0, updated.display_order)
        self.assertTrue(updated.is_primary)

        promoted = db.upsert_artifact(
            run_id=run.id, path="appendix.md", full_path=second_path,
            source_tool="write_file", is_primary=True,
        )
        ordered = db.list_artifacts(run.id)
        self.assertEqual(["appendix.md", "main.md"], [item.path for item in ordered])
        self.assertTrue(promoted.is_primary)
        self.assertEqual(1, sum(1 for item in ordered if item.is_primary))

        set_current_user_id(LOCAL_USER_ID)
        api_items = runs_router.list_run_artifacts(run.id)["artifacts"]
        self.assertEqual(["appendix.md", "main.md"], [item["path"] for item in api_items])
        self.assertEqual([True, False], [item["is_primary"] for item in api_items])
        self.assertEqual([1, 0], [item["display_order"] for item in api_items])

    def test_failed_run_retries_as_new_related_paused_run(self) -> None:
        run, _ = self._run()
        db.set_run_status(run.id, "failed", error_code="tool_error", error_message="boom")
        retry, created = db.create_retry_run(run.id, LOCAL_USER_ID, "retry-1")
        replay, replay_created = db.create_retry_run(run.id, LOCAL_USER_ID, "retry-1")
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(retry.id, replay.id)
        self.assertEqual(run.id, retry.retry_of)
        self.assertEqual("paused", retry.status)

    def test_project_viewer_can_read_but_cannot_review(self) -> None:
        project = db.create_project(owner_id=LOCAL_USER_ID, name="shared")
        session = db.create_session(
            owner_id=LOCAL_USER_ID, title="shared run", kind="projexec", project_id=project.id,
        )
        run, _ = db.create_run(
            session_id=session.id, owner_id=LOCAL_USER_ID, project_id=project.id,
            mode="exec", workspace=f"projects/{project.id}",
        )
        path = settings.WORKSPACE_ROOT / "projects" / project.id / "result.txt"
        path.parent.mkdir(parents=True)
        path.write_text("ok", encoding="utf-8")
        artifact = db.upsert_artifact(
            run_id=run.id, path="result.txt", full_path=path, source_tool="write_file",
        )
        viewer = db.create_user(name="viewer", password="pw", role=Role.VIEWER)
        stranger = db.create_user(name="stranger", password="pw")
        db.add_project_member(project.id, viewer.id, Role.VIEWER)
        self.assertIsNotNone(db.get_run_for(run.id, viewer.id))
        self.assertIsNone(db.get_run_for(run.id, stranger.id))
        set_current_user_id(viewer.id)
        with self.assertRaises(HTTPException) as raised:
            runs_router.review_artifact(
                artifact.id, runs_router.ReviewArtifactBody(status="accepted")
            )
        self.assertEqual(403, raised.exception.status_code)

    def test_runtime_write_file_emits_and_persists_artifact(self) -> None:
        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def fake_stream(messages, **_kwargs):
            if not any(message.get("role") == "tool" for message in messages):
                yield Delta(
                    tool_calls=[ToolCallDelta(
                        index=0, id="call-write", name="write_file",
                        arguments=json.dumps({"path": "deliverable.md", "content": "# Real output"}),
                    )],
                    usage={"prompt_tokens": 10, "completion_tokens": 2},
                )
            else:
                yield Delta(content="已完成。", usage={"prompt_tokens": 12, "completion_tokens": 4})

        async def collect():
            chunks = []
            async for chunk in runtime.run_chat(self.session, db.get_user(LOCAL_USER_ID), "生成交付物"):
                chunks.append(chunk)
            return chunks

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            chunks = asyncio.run(collect())

        payload = "".join(chunks)
        self.assertIn("event: run", payload)
        self.assertIn("event: artifact", payload)
        runs = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)
        self.assertEqual(1, len(runs))
        self.assertEqual("completed", runs[0].status)
        self.assertIn("workspace.write", runs[0].permission_snapshot["permissions"])
        self.assertEqual(
            {"permissions": ["workspace.write"], "timeout_seconds": 30.0, "isolation": "thread"},
            runs[0].permission_snapshot["tool_policies"]["write_file"],
        )
        artifacts = db.list_artifacts(runs[0].id)
        self.assertEqual(["deliverable.md"], [item.path for item in artifacts])
        self.assertTrue((root / "deliverable.md").is_file())

    def test_runtime_persists_immutable_skill_release_snapshot(self) -> None:
        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def fake_stream(_messages, **_kwargs):
            yield Delta(content="完成。", usage={"prompt_tokens": 3, "completion_tokens": 1})

        snapshot = {
            "slug": "atomic-skill", "release_id": "atomic-skill@1+abc", "version": "1",
            "content_hash": "abc", "instructions_hash": "def", "tool_contract_version": "1",
            "tools": ["web_fetch"], "permissions": ["network.read"], "source": "agentmate",
            "legacy": False,
        }

        async def collect():
            return [chunk async for chunk in runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "执行技能", skills=["atomic-skill"],
            )]

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime, "skill_runtime_def", return_value={
                "instructions": "只使用已安装快照。", "tools": [], "snapshot": snapshot,
            }),
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            asyncio.run(collect())

        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual([snapshot], run.permission_snapshot["skill_releases"])

    def test_runtime_applies_stable_skill_prompt_budget_and_conflict_order(self) -> None:
        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        captured: dict[str, str] = {}

        async def fake_stream(messages, **_kwargs):
            captured["system"] = str(messages[0]["content"])
            yield Delta(content="完成。", usage={"prompt_tokens": 3, "completion_tokens": 1})

        def fake_skill(slug: str):
            return {
                "instructions": slug + ":" + ("x" * 6998),
                "tools": [],
                "snapshot": {
                    "slug": slug, "release_id": f"{slug}@1", "version": "1",
                    "content_hash": slug, "instructions_hash": slug,
                    "tool_contract_version": "1", "tools": [], "permissions": [],
                    "files": [], "package_key": slug, "source": "agentmate", "legacy": False,
                },
            }

        async def collect():
            return [chunk async for chunk in runtime.run_chat(
                self.session, db.get_user(LOCAL_USER_ID), "执行组合技能",
                skills=["first-skill", "second-skill", "third-skill"],
            )]

        root = settings.WORKSPACE_ROOT / "default"
        with (
            patch.object(runtime, "skill_runtime_def", side_effect=fake_skill),
            patch.object(runtime, "stream_chat", side_effect=fake_stream),
            patch.object(runtime, "resolve_model_config", return_value=("test", "http://test", "key", "/chat")),
            patch.object(runtime, "workspace_root", return_value=root),
            patch.object(runtime.memory, "capture_enabled", return_value=False),
            patch.object(runtime.telemetry, "chat_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "generation_observation", side_effect=noop_observation),
            patch.object(runtime.telemetry, "tool_observation", side_effect=noop_observation),
        ):
            chunks = asyncio.run(collect())

        payload = "".join(chunks)
        self.assertIn("技能预算未加载 third-skill", payload)
        self.assertIn("技能指令已截断 second-skill", payload)
        self.assertIn("用户明确要求 > 项目规范 > 上述 loadout 顺序", captured["system"])
        self.assertNotIn("third-skill:", captured["system"])
        run = db.list_runs(LOCAL_USER_ID, session_id=self.session.id)[0]
        self.assertEqual(
            ["first-skill", "second-skill"],
            [item["slug"] for item in run.permission_snapshot["skill_releases"]],
        )


if __name__ == "__main__":
    unittest.main()
