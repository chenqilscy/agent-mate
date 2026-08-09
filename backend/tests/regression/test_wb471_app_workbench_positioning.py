"""WB-471 product-surface positioning regressions."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class AppWorkbenchPositioningContractTest(unittest.TestCase):
    def test_app_is_the_personal_workbench_across_current_surfaces(self) -> None:
        sidebar = read("src/components/layout/Sidebar.tsx")
        home = read("src/views/HomeView.tsx")
        projects = read("src/views/WorkspaceContextsView.tsx")
        handoff = read("src/views/ConsoleHandoffView.tsx")

        self.assertIn("label: '个人工作台'", sidebar)
        self.assertIn("你的 Agent 工作台", home)
        self.assertIn("组织任务、发起 Run，并监督和验收 Agent 工作", home)
        self.assertIn("App 负责推进工作，Console 负责项目治理", projects)
        self.assertIn("App 是你的个人 Agent 工作台", handoff)

    def test_local_agent_is_an_execution_node_not_the_app_product_definition(self) -> None:
        current_surfaces = "\n".join((
            read("README.md"),
            read("docs/agentmate-server-first-架构设计.md"),
            read("src/views/HomeView.tsx"),
            read("src/views/WorkspaceContextsView.tsx"),
            read("src/views/ConsoleHandoffView.tsx"),
        ))

        self.assertIn("Console manages the system", current_surfaces)
        self.assertIn("App（个人 Agent 工作台）", current_surfaces)
        self.assertIn("Console 管理系统，App 使用系统完成工作，Local Agent 在设备上实际执行", current_surfaces)
        self.assertNotIn("Local Agent 的桌面控制面", current_surfaces)
        self.assertNotIn("Local Agent 工作台", current_surfaces)
        self.assertNotIn("你的本机 AI 执行工作台", current_surfaces)
        self.assertNotIn("AgentMate Local Agent** 是安装在用户设备上的桌面客户端", current_surfaces)
        self.assertIn("它不包含 App UI", current_surfaces)
        self.assertIn('App["App<br/>个人 Agent 工作台"]', current_surfaces)
        self.assertIn('LocalAgent["Local Agent<br/>后台执行节点', current_surfaces)

    def test_device_configuration_is_secondary_to_the_work_loop(self) -> None:
        home = read("src/views/HomeView.tsx")
        settings = read("src/components/settings/SettingsModal.tsx")
        architecture = read("docs/agentmate-server-first-架构设计.md")

        self.assertIn(">运行设置</WbButton>", home)
        self.assertIn("label: '运行设置'", settings)
        self.assertNotIn(">此设备</WbButton>", home)
        self.assertIn("App 的“执行概览”", architecture)
        self.assertIn("App 的“运行设置”", architecture)
        self.assertIn("App 的“模型管理”和“本机能力”", architecture)
        self.assertIn("Local Agent 是当前默认的本机执行节点", architecture)


if __name__ == "__main__":
    unittest.main()
