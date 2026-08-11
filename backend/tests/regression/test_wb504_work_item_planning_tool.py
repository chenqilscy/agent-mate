"""WB-504 App Agent planning tool uses only Server IDs and CAS versions."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agent import tools
import server_client


class WorkItemPlanningToolTest(unittest.TestCase):
    def tearDown(self) -> None:
        tools.set_work_context(None, None)

    def test_list_exposes_real_sprints_and_versions_then_update_traces_cas(self) -> None:
        tools.set_work_context("project-504", "member-504", server_token="token-504")
        with (
            patch.object(server_client, "list_work_items", return_value=[{
                "id": "item-504", "title": "加入 Sprint", "status": "todo", "version": 7,
                "sprint_id": "", "milestone_id": "",
            }]),
            patch.object(server_client, "list_project_sprints", return_value=[{
                "id": "sprint-504", "name": "Sprint 7", "status": "active", "milestone_id": "mile-504",
            }]),
        ):
            listed = tools._list_work_items_run({})
        self.assertIn("item-504", listed.text)
        self.assertIn("version=7", listed.text)
        self.assertIn("sprint-504", listed.text)

        with patch.object(server_client, "update_work_item_planning", return_value={
            "id": "item-504", "project_id": "project-504", "title": "加入 Sprint",
            "status": "todo", "sprint_id": "sprint-504", "sprint_name": "Sprint 7",
            "milestone_id": "mile-504", "version": 8,
            "previous_sprint_id": "sprint-previous", "previous_milestone_id": "mile-previous",
        }) as update:
            outcome = tools._update_work_item_planning_run({
                "item_id": "item-504", "sprint_id": "sprint-504",
                "expected_version": 7, "sync_milestone": True,
            })
        update.assert_called_once_with(
            "token-504", "project-504", "item-504", sprint_id="sprint-504",
            expected_version=7, sync_milestone=True,
        )
        self.assertIn("version=7→8", outcome.text)
        self.assertEqual("update_work_item_planning", outcome.trace[0]["tool"])
        self.assertEqual("member-504", outcome.trace[0]["actor_id"])
        self.assertEqual("sprint-previous", outcome.trace[0]["old_sprint_id"])
        self.assertEqual(7, outcome.trace[0]["from_version"])
        self.assertEqual(8, outcome.trace[0]["to_version"])
        self.assertEqual("sprint-504", outcome.live[0]["sprint_id"])

    def test_server_rejection_and_offline_never_fall_back_to_local_write(self) -> None:
        tools.set_work_context("project-504", "viewer-504", server_token="token-504")
        rejection = server_client.ServerRejected(409, "work item version conflict")
        with patch.object(server_client, "update_work_item_planning", side_effect=rejection):
            outcome = tools._update_work_item_planning_run({
                "item_id": "item-504", "sprint_id": "sprint-504", "expected_version": 3,
            })
        self.assertIn("409", outcome.text)
        self.assertIn("未发生部分写入", outcome.text)
        self.assertFalse(outcome.trace)

        tools.set_work_context("project-504", "member-504")
        offline = tools._update_work_item_planning_run({
            "item_id": "item-504", "sprint_id": "sprint-504", "expected_version": 3,
        })
        self.assertIn("未修改本地镜像", offline.text)

    def test_tool_is_contextual_write_and_absent_from_plan_mode(self) -> None:
        with patch.object(tools, "server_tool_enabled", return_value=True):
            exec_names = [tool.name for tool in tools.work_item_tools(plan=False, include_project=True)]
            plan_names = [tool.name for tool in tools.work_item_tools(plan=True, include_project=True)]
        self.assertIn("update_work_item_planning", exec_names)
        self.assertNotIn("update_work_item_planning", plan_names)
        self.assertEqual(("project.write",), tools.update_work_item_planning.permissions)
