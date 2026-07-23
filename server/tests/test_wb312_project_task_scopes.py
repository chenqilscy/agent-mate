"""WB-312: project execution must be scoped to a Sprint."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ProjectTaskScopeContractTests(unittest.TestCase):
    def test_sprint_board_has_a_real_execution_scope(self) -> None:
        source = (
            ROOT
            / "console"
            / "src"
            / "components"
            / "project"
            / "ProjectWorkspace.tsx"
        ).read_text(encoding="utf-8")
        for marker in (
            'nextSprints.find((sprint) => sprint.status === "active")?.id || ""',
            'items.filter((item) => item.sprint_id === selectedSprint.id)',
            'sprintItems.filter((item) => !item.parent_id)',
            "状态、WIP、拖拽和完成率只统计当前选择的 Sprint。",
            "项目看板不会回退到全项目任务",
            'sprint_id: selectedSprint.id',
            'const task = sprintRoots.find((item) => item.id === id);',
        ):
            self.assertIn(marker, source)

    def test_backlog_and_all_tasks_are_separate_list_scopes(self) -> None:
        source = (
            ROOT
            / "console"
            / "src"
            / "components"
            / "project"
            / "ProjectWorkspace.tsx"
        ).read_text(encoding="utf-8")
        for marker in (
            'type ProjectTaskListScope = "backlog" | "all";',
            'scope === "backlog"',
            "items.filter((item) => !item.sprint_id)",
            "这里只保留尚未进入 Sprint 的任务",
            "跨里程碑、跨 Sprint 查询和批量维护项目任务",
        ):
            self.assertIn(marker, source)

    def test_project_navigation_separates_execution_and_planning(self) -> None:
        source = (
            ROOT / "console" / "src" / "pages" / "ProjectDetailPage.tsx"
        ).read_text(encoding="utf-8")
        for marker in (
            '{ key: "plan", label: "当前 Sprint" }',
            '{ key: "backlog", label: "Backlog" }',
            '{ key: "tasks", label: "全部任务" }',
            '{ key: "milestones", label: "里程碑" }',
            '{ key: "sprints", label: "Sprint" }',
            'return <ProjectTasks scope="backlog" />;',
            'return <ProjectIterations sectionOnly="sprints" />;',
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
