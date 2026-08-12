"""WB-471 positioning contract, superseded by WB-517/WB-518 boundaries."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class AppWorkbenchPositioningContractTest(unittest.TestCase):
    def test_workspace_owns_business_and_desktop_owns_local_execution(self) -> None:
        sidebar = read("src/components/layout/Sidebar.tsx")
        home = read("src/views/HomeView.tsx")
        handoff = read("src/views/ConsoleHandoffView.tsx")

        self.assertIn("label: '本机执行节点'", sidebar)
        self.assertIn("label: '执行与授权'", sidebar)
        self.assertIn("Desktop Companion", home)
        self.assertIn("执行节点状态", home)
        self.assertIn("Desktop Companion 只保留本机执行", handoff)
        self.assertFalse((ROOT / "src/views/WorkspaceContextsView.tsx").exists())
        self.assertFalse((ROOT / "src/views/ProjectHomeView.tsx").exists())

    def test_local_agent_is_an_execution_node_not_a_business_api(self) -> None:
        current_surfaces = "\n".join((
            read("README.md"),
            read("docs/agentmate-server-first-架构设计.md"),
            read("src/views/HomeView.tsx"),
        ))

        self.assertIn("Workspace is the primary end-user surface", current_surfaces)
        self.assertIn("Desktop Companion | 执行节点的可信本机控制面", current_surfaces)
        self.assertIn("Local Agent Core 已就绪", current_surfaces)
        self.assertIn("提供业务 CRUD、账号权威或用户业务 UI", current_surfaces)
        self.assertNotIn("App 是你的个人 Agent 工作台", current_surfaces)

    def test_device_configuration_supports_the_local_execution_loop(self) -> None:
        home = read("src/views/HomeView.tsx")
        settings = read("src/components/settings/SettingsModal.tsx")
        architecture = read("docs/agentmate-server-first-架构设计.md")

        self.assertIn(">运行设置</WbButton>", home)
        self.assertIn("label: '运行设置'", settings)
        self.assertIn("Desktop Companion 的执行诊断中心", architecture)
        self.assertIn("管理模型、Skill、设备运行设置以及本机 MCP/连接器", architecture)
        self.assertIn("个人电脑或专用机器上的后台执行节点", architecture)


if __name__ == "__main__":
    unittest.main()
