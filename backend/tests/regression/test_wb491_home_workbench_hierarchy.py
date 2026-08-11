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

        self.assertIn('需要我处理', home)
        self.assertIn('我的行动项', home)
        self.assertIn('真实 Session / Run 状态', home)
        self.assertIn('className="home-status-empty"', home)
        self.assertIn("waiting_user: '等待你的回答'", home)
        self.assertIn("waiting_approval: '等待授权'", home)
        self.assertNotIn('className="home-device-status"', home)
        self.assertNotIn('最近完成', home)

    def test_run_rows_and_empty_state_have_readable_density(self) -> None:
        css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")

        self.assertIn('.home-run { width: 100%; min-width: 0; min-height: 52px;', css)
        self.assertIn('.home-run-group .ant-list-items { display: flex; flex-direction: column; gap: 6px; }', css)
        self.assertIn('.home-status-empty { min-height: 40px;', css)
        self.assertIn('.home-run-body small { color: var(--text-2); font-size: 11.5px;', css)


if __name__ == "__main__":
    unittest.main()
