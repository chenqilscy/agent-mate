"""WB-496 global WorkItem selection hands off to one authoritative Server Run."""
from __future__ import annotations

import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from agent import tools
from agent import tool_execution, tool_worker
from config import settings
import local_agent_store
import run_transport


class GlobalWorkActionRunHandoffTest(unittest.TestCase):
    def tearDown(self) -> None:
        tools.set_work_context(None, None)

    @staticmethod
    def _item(*, assignee: str = "owner-496", status: str = "todo") -> dict:
        return {
            "id": "work-496", "project_id": "project-496", "title": "处理真实任务",
            "description": "生成可验收交付物", "assignee": assignee, "status": status,
        }

    @staticmethod
    def _started(*, duplicate: bool = False) -> dict:
        return {
            "session": {"id": "session-496"},
            "run": {"id": "run-496"},
            "duplicate": duplicate,
        }

    def _context(self) -> None:
        tools.set_work_context(
            None, "owner-496", account_server_token="token-496", session_id="source-session-496",
        )

    def test_explicit_selection_stages_local_input_and_creates_idempotent_server_run(self) -> None:
        self._context()
        with (
            patch.object(tools.server_client, "list_work_items", return_value=[self._item()]),
            patch.object(run_transport, "ensure_device", return_value="device-token") as ensure,
            patch.object(run_transport, "device_id", return_value="device-496"),
            patch.object(local_agent_store, "stage_run_input") as stage,
            patch.object(local_agent_store, "clear_run_input") as clear,
            patch.object(
                tools.server_client, "execute_server_work_item", return_value=self._started(),
            ) as execute,
        ):
            first = tools._start_work_item_run_run({
                "project_id": "project-496", "work_item_id": "work-496",
            })
            second = tools._start_work_item_run_run({
                "project_id": "project-496", "work_item_id": "work-496",
            })

        ensure.assert_called_with("owner-496", "token-496")
        self.assertEqual(2, stage.call_count)
        first_key = execute.call_args_list[0].kwargs["idempotency_key"]
        self.assertEqual(first_key, execute.call_args_list[1].kwargs["idempotency_key"])
        self.assertEqual(first_key, execute.call_args_list[0].kwargs["local_input_key"])
        self.assertEqual("device-496", execute.call_args_list[0].kwargs["target_device_id"])
        self.assertIn("session_id=session-496", first.text)
        self.assertIn("run_id=run-496", first.text)
        self.assertEqual("doing", first.live[0]["status"])
        self.assertTrue(first.terminal)
        clear.assert_not_called()
        self.assertIn("已创建执行", second.text)

    def test_other_member_completed_and_missing_device_fail_before_server_write(self) -> None:
        self._context()
        for item, expected in (
            (self._item(assignee="other-owner"), "已分配给其他成员"),
            (self._item(status="done"), "已完成"),
        ):
            with (
                patch.object(tools.server_client, "list_work_items", return_value=[item]),
                patch.object(tools.server_client, "execute_server_work_item") as execute,
            ):
                result = tools._start_work_item_run_run({
                    "project_id": "project-496", "work_item_id": "work-496",
                })
            self.assertIn(expected, result.text)
            execute.assert_not_called()

        with (
            patch.object(tools.server_client, "list_work_items", return_value=[self._item()]),
            patch.object(run_transport, "ensure_device", return_value=None),
            patch.object(local_agent_store, "stage_run_input") as stage,
            patch.object(tools.server_client, "execute_server_work_item") as execute,
        ):
            result = tools._start_work_item_run_run({
                "project_id": "project-496", "work_item_id": "work-496",
            })
        self.assertIn("设备无法在 Server 注册", result.text)
        stage.assert_not_called()
        execute.assert_not_called()

    def test_server_rejection_clears_staging_and_preserves_reason(self) -> None:
        self._context()
        rejected = tools.server_client.ServerRejected(403, "viewer cannot write")
        with (
            patch.object(tools.server_client, "list_work_items", return_value=[self._item()]),
            patch.object(run_transport, "ensure_device", return_value="device-token"),
            patch.object(run_transport, "device_id", return_value="device-496"),
            patch.object(local_agent_store, "stage_run_input"),
            patch.object(local_agent_store, "clear_run_input") as clear,
            patch.object(tools.server_client, "execute_server_work_item", side_effect=rejected),
        ):
            result = tools._start_work_item_run_run({
                "project_id": "project-496", "work_item_id": "work-496",
            })
        self.assertIn("403", result.text)
        self.assertIn("viewer cannot write", result.text)
        clear.assert_called_once()

    def test_personal_query_uses_the_local_timezone_calendar_date(self) -> None:
        self._context()

        class ShanghaiDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 8, 11, 0, 5, tzinfo=timezone(timedelta(hours=8)))

        remote = {
            "as_of": "2026-08-11", "computed_at": 0, "summary": {},
            "items": [], "unassigned": [],
        }
        with (
            patch.object(tools, "datetime", ShanghaiDateTime),
            patch.object(tools.server_client, "get_personal_action_items", return_value=remote) as query,
        ):
            result = tools._list_my_action_items_run({})
        query.assert_called_once_with("token-496", "2026-08-11")
        self.assertIn("2026-08-11", result.text)
        self.assertIn("本机时区", result.text)

    def test_isolated_tool_worker_receives_hot_loaded_server_origin(self) -> None:
        self._context()
        old_url = settings.AGENTMATE_SERVER_URL
        try:
            settings.AGENTMATE_SERVER_URL = "http://127.0.0.1:8100"
            with patch.object(tool_execution, "current_root", return_value=Path.cwd()):
                payload = json.loads(tool_execution._worker_payload(
                    tools.list_my_action_items, {}, "owner-496",
                ))
            self.assertEqual(
                "http://127.0.0.1:8100", payload["config"]["server_url"],
            )

            settings.AGENTMATE_SERVER_URL = ""
            tool_worker._configure_paths(payload)
            self.assertEqual("http://127.0.0.1:8100", settings.AGENTMATE_SERVER_URL)
        finally:
            settings.AGENTMATE_SERVER_URL = old_url


if __name__ == "__main__":
    unittest.main()
