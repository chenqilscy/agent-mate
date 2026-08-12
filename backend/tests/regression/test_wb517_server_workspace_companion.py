"""WB-517: Server Workspace is the user surface; Desktop stays execution-only."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ServerWorkspaceCompanionContractTest(unittest.TestCase):
    def test_server_root_is_personal_workspace_and_admin_overview_is_separate(self) -> None:
        app = (ROOT / "console" / "src" / "App.tsx").read_text(encoding="utf-8")
        workspace = (ROOT / "console" / "src" / "pages" / "WorkspacePage.tsx").read_text(
            encoding="utf-8"
        )
        api = (ROOT / "console" / "src" / "workspaceApi.ts").read_text(encoding="utf-8")

        self.assertIn('case "/": return <WorkspacePage account={account} />', app)
        self.assertIn('case "/admin": return <OverviewPage account={account} />', app)
        self.assertIn('name: "我的工作台"', app)
        self.assertIn('name: "管理总览"', app)
        for endpoint in (
            "/work-items/action-items",
            "/runs?limit=100",
            "/sessions?limit=100",
        ):
            self.assertIn(endpoint, api)
        for marker in ("我的行动项", "需要我处理", "最近执行", "执行节点"):
            self.assertIn(marker, workspace)
        self.assertIn("Desktop Companion", workspace)

    def test_desktop_surface_is_companion_for_local_trust_boundary(self) -> None:
        sidebar = (ROOT / "src" / "components" / "layout" / "Sidebar.tsx").read_text(
            encoding="utf-8"
        )
        home = (ROOT / "src" / "views" / "HomeView.tsx").read_text(encoding="utf-8")
        handoff = (ROOT / "src" / "views" / "ConsoleHandoffView.tsx").read_text(
            encoding="utf-8"
        )
        execution = (
            ROOT / "console" / "src" / "components" / "project" / "WorkItemExecution.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("AgentMate Desktop", sidebar)
        self.assertIn("本机执行节点", sidebar)
        self.assertIn("Desktop Companion", home)
        self.assertIn("打开 Server Workspace", home)
        self.assertIn("本机执行、可信授权、文件、凭据和诊断", handoff)
        self.assertIn("需要在执行节点处理", execution)
        self.assertNotIn("需要在 App 端处理", execution)

        settings = (ROOT / "src" / "components" / "settings" / "SettingsModal.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Desktop Companion 只使用登录身份", settings)
        self.assertFalse((ROOT / "src" / "views" / "WorkspaceContextsView.tsx").exists())
        self.assertFalse((ROOT / "src" / "views" / "ProjectHomeView.tsx").exists())


if __name__ == "__main__":
    unittest.main()
