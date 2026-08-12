from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class AppWorkspaceCoherenceContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sidebar = (ROOT / "src" / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")
        self.execution = (ROOT / "src" / "views" / "ProjExecView.tsx").read_text(encoding="utf-8")
        self.capabilities = (ROOT / "src" / "views" / "ExpertsView.tsx").read_text(encoding="utf-8")

    def test_primary_navigation_has_one_task_and_capability_model(self) -> None:
        self.assertIn("label: '本机执行节点'", self.sidebar)
        self.assertIn("label: '执行与授权'", self.sidebar)
        self.assertIn("label: '本机能力'", self.sidebar)
        self.assertIn('aria-label="最近执行"', self.sidebar)
        self.assertNotIn("label: '项目任务'", self.sidebar)
        self.assertNotIn("label: '项目上下文'", self.sidebar)
        self.assertNotIn('aria-label="Server 管理"', self.sidebar)
        self.assertNotIn("label: `任务 (", self.sidebar)
        self.assertNotIn("label: `空间 (", self.sidebar)
        self.assertNotIn("label: `自动化 (", self.sidebar)

    def test_server_execution_history_exposes_freshness(self) -> None:
        chat_store = (ROOT / "src" / "stores" / "chatStore.ts").read_text(encoding="utf-8")
        channels = (ROOT / "src" / "lib" / "channels.ts").read_text(encoding="utf-8")
        api = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("serverGetAll<SessionInfo>('/sessions', 'sessions')", api)
        self.assertIn("Authorization: `Bearer ${token}`", channels)
        self.assertIn("sessionsLoading", chat_store)
        self.assertIn("sessionsError", chat_store)
        self.assertIn("sessionsUpdatedAt", chat_store)
        self.assertIn("Server 执行记录读取失败", chat_store)
        self.assertIn("显示上次同步结果", self.sidebar)

    def test_project_and_work_items_do_not_silently_turn_errors_into_empty_data(self) -> None:
        project_store = (ROOT / "src" / "stores" / "projectStore.ts").read_text(encoding="utf-8")
        work_item_store = (ROOT / "src" / "stores" / "workItemStore.ts").read_text(encoding="utf-8")

        self.assertIn("Server 项目读取失败", project_store)
        self.assertNotIn("/* backend down */", project_store)
        self.assertIn("const projectChanged", work_item_store)
        self.assertIn("Server 任务读取失败", work_item_store)
        self.assertIn("updatedAt: Date.now()", work_item_store)

    def test_task_inbox_and_run_workbench_are_one_round_trip(self) -> None:
        self.assertIn("executionReadOnly", self.execution)
        self.assertIn("<RunLaunchHandoff", self.execution)
        self.assertIn("<PePanel messages={messages}", self.execution)
        self.assertIn("← 返回当前执行", self.capabilities)
        self.assertIn("setView('projexec'", self.capabilities)


if __name__ == "__main__":
    unittest.main()
