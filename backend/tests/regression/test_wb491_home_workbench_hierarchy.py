from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class HomeWorkbenchHierarchyContractTests(unittest.TestCase):
    def test_workbench_navigation_is_separate_from_new_task_action(self) -> None:
        sidebar = (ROOT / "src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
        settings = (ROOT / "src/components/settings/SettingsModal.tsx").read_text(encoding="utf-8")

        self.assertIn("{ id: 'home', label: '工作台'", sidebar)
        self.assertIn('className="sb-new-task" onClick={newTask}', sidebar)
        self.assertIn("onClick={({ key }) => setView(key as ViewId)}", sidebar)
        self.assertIn('<option value="home">工作台</option>', settings)

    def test_home_summary_prioritizes_actionable_run_state(self) -> None:
        home = (ROOT / "src/views/HomeView.tsx").read_text(encoding="utf-8")

        self.assertIn('title="等待我确认"', home)
        self.assertIn('title="近 7 天失败"', home)
        self.assertIn('你的 Run 与待处理事项', home)
        self.assertIn('className="home-status-empty"', home)
        self.assertIn("if (session.project_id) return '项目 Run'", home)
        self.assertNotIn('className="home-device-status"', home)
        self.assertNotIn('title="近 7 天 Run"', home)

    def test_run_rows_and_empty_state_have_readable_density(self) -> None:
        css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")

        self.assertIn('.home-run { width: 100%; min-width: 0; min-height: 52px;', css)
        self.assertIn('.home-run-group .ant-list-items { display: flex; flex-direction: column; gap: 6px; }', css)
        self.assertIn('.home-status-empty { min-height: 40px;', css)
        self.assertIn('.home-run-body small { color: var(--text-2); font-size: 11.5px;', css)


if __name__ == "__main__":
    unittest.main()
