from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class HomeWorkbenchHierarchyContractTests(unittest.TestCase):
    def test_execution_control_is_separate_from_new_task_action(self) -> None:
        sidebar = (ROOT / "src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
        settings = (ROOT / "src/components/settings/SettingsModal.tsx").read_text(encoding="utf-8")

        self.assertIn("{ id: 'home', label: '执行与授权'", sidebar)
        self.assertIn('className="sb-new-task" onClick={newTask}', sidebar)
        self.assertIn("onClick={({ key }) => setView(key as ViewId)}", sidebar)
        self.assertIn('<option value="home">执行与授权</option>', settings)

    def test_home_prioritizes_real_execution_node_state(self) -> None:
        home = (ROOT / "src/views/HomeView.tsx").read_text(encoding="utf-8")

        for marker in ("执行节点状态", "活动租约", "待回执事件", "发起本机执行"):
            self.assertIn(marker, home)
        self.assertIn('className="home-status-empty is-muted"', home)
        self.assertNotIn("我的行动项", home)
        self.assertNotIn("需要我处理", home)
        self.assertNotIn("真实 Session / Run 状态", home)

    def test_local_rows_and_empty_state_have_readable_density(self) -> None:
        css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")

        self.assertIn('.home-run { width: 100%; min-width: 0; min-height: 52px;', css)
        self.assertIn('.home-status-empty { min-height: 40px;', css)
        self.assertIn('.home-run-body small { color: var(--text-2); font-size: 11.5px;', css)
        self.assertIn('@media (max-width: 640px)', css)


if __name__ == "__main__":
    unittest.main()
