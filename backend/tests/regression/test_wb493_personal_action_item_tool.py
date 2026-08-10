"""WB-493 global work queries use Server authority instead of workspace guesses."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent import runtime, tools
from agent.llm import Delta
from config import settings
from storage import db
from storage.models import LOCAL_USER_ID


class PersonalActionItemToolTest(unittest.TestCase):
    def tearDown(self) -> None:
        tools.set_work_context(None, None)

    @staticmethod
    def _remote() -> dict:
        return {
            "as_of": "2026-08-10",
            "source": "server",
            "summary": {"assigned": 1, "unassigned": 1, "backlog": 2},
            "items": [{
                "id": "assigned-493", "title": "真实 Console 任务", "status": "doing",
                "priority": "urgent", "due_date": "2026-08-10",
                "action_signals": ["due_today", "in_progress"],
                "project": {"id": "project-493", "name": "玖月", "role": "Member"},
            }],
            "unassigned": [{
                "id": "unassigned-493", "title": "未分配任务", "status": "todo",
                "priority": "high", "due_date": "2026-08-10",
                "action_signals": ["due_today"],
                "project": {"id": "project-493", "name": "玖月", "role": "Member"},
            }],
        }

    def test_global_tool_uses_account_server_token_and_stable_work_item_ids(self) -> None:
        tools.set_work_context(None, "owner-493", account_server_token="account-token-493")
        with (
            patch.object(tools.server_client, "get_personal_action_items", return_value=self._remote()) as remote,
            patch.object(tools.db, "list_work_items", side_effect=AssertionError("must not read local mirror")),
        ):
            result = tools._list_my_action_items_run({})

        remote.assert_called_once()
        self.assertEqual("account-token-493", remote.call_args.args[0])
        self.assertIn("真实 Console 任务", result.text)
        self.assertIn("work_item_id=assigned-493", result.text)
        self.assertIn("不计入我的任务", result.text)
        self.assertIn("来源=AgentMate Server", result.text)

    def test_server_failure_does_not_fall_back_to_files_or_local_tasks(self) -> None:
        tools.set_work_context(None, "owner-493", account_server_token="account-token-493")
        with (
            patch.object(tools.server_client, "get_personal_action_items", return_value=None),
            patch.object(tools.db, "list_work_items", side_effect=AssertionError("must not read local mirror")),
        ):
            result = tools._list_my_action_items_run({})
        self.assertIn("Server 当前不可达", result.text)
        self.assertIn("未使用本机文件或缓存推测任务", result.text)

    def test_toolset_is_global_read_only_and_project_writes_remain_scoped(self) -> None:
        with patch.object(tools, "server_tool_enabled", return_value=True):
            global_names = [tool.name for tool in tools.work_item_tools(plan=False, include_project=False)]
            project_names = [tool.name for tool in tools.work_item_tools(plan=False, include_project=True)]
            plan_names = [tool.name for tool in tools.work_item_tools(plan=True, include_project=True)]
        self.assertEqual(["list_my_action_items"], global_names)
        self.assertEqual(
            ["list_my_action_items", "list_work_items", "set_work_item_status"], project_names,
        )
        self.assertEqual(["list_my_action_items", "list_work_items"], plan_names)


class PersonalActionItemRuntimeTest(unittest.TestCase):
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
        db.set_server_identity(LOCAL_USER_ID, "account-token-493")

    def tearDown(self) -> None:
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
        db._local = threading.local()

    def test_global_run_exposes_server_inbox_and_forbids_workspace_guessing(self) -> None:
        session = db.create_session(owner_id=LOCAL_USER_ID, title="今日任务")
        captured: dict[str, object] = {}

        async def fake_stream(messages, **kwargs):
            captured["system"] = str(messages[0]["content"])
            captured["tools"] = {
                item["function"]["name"] for item in kwargs.get("tools", [])
                if item.get("function")
            }
            yield Delta(content="已读取。", usage={"prompt_tokens": 5, "completion_tokens": 2})

        class NoopObservation:
            def update(self, **_kwargs):
                pass

        @contextmanager
        def noop_observation(**_kwargs):
            yield NoopObservation()

        async def collect() -> list[str]:
            return [chunk async for chunk in runtime.run_chat(
                session, db.get_user(LOCAL_USER_ID), "今天有哪些任务需要处理？",
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

        self.assertIn("list_my_action_items", captured["tools"])
        self.assertIn("必须先调用 list_my_action_items", captured["system"])
        self.assertIn("不得扫描工作区文件", captured["system"])
        run = db.list_runs(LOCAL_USER_ID, session_id=session.id)[0]
        self.assertIn("list_my_action_items", run.permission_snapshot["tools"])


if __name__ == "__main__":
    unittest.main()
