from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ProjectBindingsContractTest(unittest.TestCase):
    def test_project_sidebar_exposes_real_assistant_and_automation_bindings(self) -> None:
        source = (ROOT / "src" / "views" / "ProjectHomeView.tsx").read_text(encoding="utf-8")

        self.assertIn("item.workspace === `project:${project.id}`", source)
        self.assertIn("item.project_id === project.id", source)
        self.assertIn("bindingSection('assistant', '助手')", source)
        self.assertIn("bindingSection('automation', '自动化')", source)
        self.assertIn("canManage && <span className=\"add\"", source)

    def test_binding_editor_does_not_steal_objects_from_other_projects(self) -> None:
        source = (ROOT / "src" / "components" / "project" / "ProjectBindingsModal.tsx").read_text(encoding="utf-8")

        self.assertIn("item.workspace === 'dedicated'", source)
        self.assertIn("item.workspace !== projectWorkspace", source)
        self.assertIn("{ workspace: 'default' }", source)
        self.assertIn("{ workspace: projectWorkspace }", source)
        self.assertIn("{ project_id: null }", source)
        self.assertIn("{ project_id: project.id }", source)
        self.assertIn("if (!item.project_id && selected.has(item.id))", source)
        self.assertIn("await readBack()", source)


if __name__ == "__main__":
    unittest.main()
