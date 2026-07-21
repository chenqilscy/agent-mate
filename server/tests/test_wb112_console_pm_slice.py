from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "console" / "src" / "components" / "project" / "ProjectWorkspace.tsx"


class WB112ConsolePMSliceContractTests(unittest.TestCase):
    def test_project_scoped_templates_still_create_tasks_through_server_api(self) -> None:
        source = WORKSPACE.read_text(encoding="utf-8")

        for marker in (
            "agentmate.console.pm.templates.${project.id}",
            "存为任务模板",
            "使用模板",
            "删除任务模板",
            "consoleApi.createWorkItem",
        ):
            self.assertIn(marker, source)

        self.assertNotIn("localStorage.setItem(\"work_items\"", source)


if __name__ == "__main__":
    unittest.main()
