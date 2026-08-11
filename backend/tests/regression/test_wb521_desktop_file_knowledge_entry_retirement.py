import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class DesktopFileKnowledgeEntryRetirementContractTests(unittest.TestCase):
    def test_aggregate_navigation_and_home_file_shortcut_are_removed(self) -> None:
        sidebar = source("src/components/layout/Sidebar.tsx")
        home = source("src/views/HomeView.tsx")

        for forbidden in ("文件与知识", "我的文件", "金山文档", "灵感", "IcCompass", "IcFolder"):
            self.assertNotIn(forbidden, sidebar)
        self.assertNotIn("['myfiles'", home)
        self.assertNotIn("本机文件", home)
        self.assertIn("本机能力", sidebar)
        self.assertIn("最近执行", sidebar)

    def test_standalone_business_pages_are_not_routable_or_bundled(self) -> None:
        app = source("src/App.tsx")
        router = source("src/lib/router.ts")
        settings = source("src/components/settings/SettingsModal.tsx")

        for retired_view in ("MyFilesView", "KdocsView"):
            self.assertNotIn(retired_view, app)
        for retired_route in ("'/inspiration'", "'/files'", "'/kdocs'"):
            self.assertNotIn(retired_route, router)
        view_ids = source("src/lib/types.ts")
        for retired_id in ("| 'inspire'", "| 'myfiles'", "| 'kdocs'"):
            self.assertNotIn(retired_id, view_ids)
        self.assertNotIn('<option value="knowledge">', settings)
        self.assertIn("system.startup_page !== 'knowledge'", app)

    def test_weknora_is_only_a_local_source_manager(self) -> None:
        connector = source("src/components/connector/ConnectorDetailModal.tsx")
        capabilities = source("src/views/ExpertsView.tsx")
        knowledge = source("src/views/KnowledgeView.tsx")

        self.assertIn("管理本机知识源", connector)
        self.assertIn("setView('knowledge')", connector)
        self.assertIn("管理本机知识源", capabilities)
        self.assertIn("可供 Server Run 调用", capabilities)
        self.assertIn("在 Workspace 使用", connector)
        self.assertIn("本机知识源", knowledge)
        self.assertIn("Server Workspace 选择", knowledge)
        for retired_copy in ("挂载到对话", "取消挂载", "已挂载", "useLoadoutStore"):
            self.assertNotIn(retired_copy, knowledge)
        self.assertNotIn("添加到本会话", connector)
        self.assertNotIn("ConnAddBtn", capabilities)
        self.assertNotIn("useLoadoutStore", capabilities)

    def test_runtime_file_and_connector_capabilities_are_preserved(self) -> None:
        project_run = source("src/views/ProjExecView.tsx")
        api = source("src/lib/api.ts")

        self.assertIn("<PePanel", project_run)
        self.assertIn("filesTree:", api)
        self.assertIn("kdocsStatus:", api)
        self.assertIn("knowledgeConfig:", api)


if __name__ == "__main__":
    unittest.main()
