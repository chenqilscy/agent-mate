from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ProjectTaskCenterContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.center = (
            ROOT / "src" / "components" / "project" / "ProjectTaskCenter.tsx"
        ).read_text(encoding="utf-8")
        self.execution = (ROOT / "src" / "views" / "ProjExecView.tsx").read_text(
            encoding="utf-8"
        )
        self.styles = (ROOT / "src" / "styles" / "app.css").read_text(
            encoding="utf-8"
        )

    def test_fresh_execution_uses_console_aligned_task_center(self) -> None:
        self.assertIn("<ProjectTaskCenter", self.execution)
        self.assertIn("projectId={project.id}", self.execution)
        self.assertIn("canWrite={canWriteProject}", self.execution)
        self.assertIn('mode="execute"', self.center)
        for label in ("全部任务", "里程碑", "Sprint"):
            self.assertIn(label, self.center)

    def test_views_use_server_authority_and_real_relations(self) -> None:
        self.assertIn("api.serverProjectSprints(projectId)", self.center)
        self.assertIn("api.listMilestones", (ROOT / "src" / "stores" / "workItemStore.ts").read_text(encoding="utf-8"))
        self.assertIn("item.milestone_id === milestone.id", self.center)
        self.assertIn("item.sprint_id === sprint.id", self.center)
        self.assertIn("item.status === 'done'", self.center)
        self.assertNotIn("mock", self.center.lower())

    def test_write_controls_follow_project_role(self) -> None:
        self.assertIn("canWrite && view === 'tasks'", self.center)
        self.assertIn("canWrite && view === 'milestones'", self.center)
        self.assertIn("canWrite && view === 'sprints'", self.center)
        self.assertIn("canWrite ? <Select", self.center)

    def test_execution_composer_has_no_green_focus_line(self) -> None:
        composer_rule = re.search(
            r'\.view\[data-view="projexec"\] \.composer:focus-within\s*\{([^}]+)\}',
            self.styles,
        )
        textarea_rule = re.search(
            r'\.view\[data-view="projexec"\] \.composer textarea\.ant-input:focus\s*\{([^}]+)\}',
            self.styles,
        )
        self.assertIsNotNone(composer_rule)
        self.assertIsNotNone(textarea_rule)
        self.assertIn("border-color: var(--text-3)", composer_rule.group(1))
        self.assertIn("box-shadow: none", composer_rule.group(1))
        self.assertIn("outline: none", textarea_rule.group(1))
        self.assertIn("box-shadow: none", textarea_rule.group(1))
        self.assertNotIn("var(--brand)", composer_rule.group(1))
        self.assertNotIn("var(--brand)", textarea_rule.group(1))

    def test_mobile_layout_stacks_plan_rows(self) -> None:
        self.assertIn(".pe-task-center { padding: 14px; }", self.styles)
        self.assertIn(".pe-plan-row { grid-template-columns: minmax(0, 1fr);", self.styles)
        self.assertIn("scroll={{ x: 860 }}", self.center)


if __name__ == "__main__":
    unittest.main()
