from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RecentExecutionProjectContextContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sidebar = (ROOT / "src" / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")
        self.styles = (ROOT / "src" / "styles" / "app.css").read_text(encoding="utf-8")
        self.business = (ROOT / "server" / "business_store.py").read_text(encoding="utf-8")

    def test_project_context_defaults_to_current_project_and_can_show_all(self) -> None:
        self.assertIn("recentScope", self.sidebar)
        self.assertIn("session.project_id === contextProjectId", self.sidebar)
        self.assertIn("route.projectId || activeProject?.id", self.sidebar)
        self.assertIn('aria-label="最近执行范围"', self.sidebar)
        self.assertIn("当前项目暂无执行", self.sidebar)
        self.assertIn("当前项目 <small>{projectSessions.length}</small>", self.sidebar)

    def test_cross_project_open_requires_an_explicit_handoff(self) -> None:
        self.assertIn("projectId !== contextProjectId", self.sidebar)
        self.assertIn("切换并打开", self.sidebar)
        self.assertIn("留在当前项目", self.sidebar)
        self.assertIn("await openSession(id)", self.sidebar)

    def test_latest_run_work_item_is_real_server_context(self) -> None:
        self.assertIn("with_latest_run_context", self.business)
        self.assertIn("LEFT JOIN work_items", self.business)
        self.assertIn("session.work_item_title", self.sidebar)
        self.assertIn("任务 · ${session.work_item_title}", self.sidebar)
        self.assertIn(".sb-run-scope button.active", self.styles)


if __name__ == "__main__":
    unittest.main()
