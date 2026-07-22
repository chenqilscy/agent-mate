from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ConsoleAntDesignEntryTests(unittest.TestCase):
    def test_console_dependencies_are_antd6_compatible(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        dependencies = package["dependencies"]
        self.assertEqual(dependencies["antd"], "6.5.1")
        # Pro Components stable 2.x does not declare antd 6 support; pin the compatible 3.x prerelease.
        self.assertEqual(dependencies["@ant-design/pro-components"], "3.1.14-2")

    def test_server_serves_react_entry_for_every_console_route(self) -> None:
        main = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
        built_index = (ROOT / "server" / "web" / "console-dist" / "index.html").read_text(encoding="utf-8")

        self.assertIn('app.mount("/console-assets", StaticFiles(directory=_CONSOLE_DIST)', main)
        self.assertIn("return _console_next_html()", main)
        self.assertIn('src="/console-assets/assets/', built_index)
        self.assertNotIn("console.html", main)
        self.assertFalse((ROOT / "server" / "web" / "console.html").exists())

    def test_skills_page_uses_professional_management_components(self) -> None:
        page = (ROOT / "console" / "src" / "SkillsPage.tsx").read_text(encoding="utf-8")
        editor = (ROOT / "console" / "src" / "SkillEditor.tsx").read_text(encoding="utf-8")

        self.assertIn("<ProTable", page)
        self.assertIn("<PageContainer", page)
        self.assertIn("<Drawer", editor)
        self.assertIn("file-workspace", editor)

    def test_all_stable_routes_have_react_pages(self) -> None:
        app = (ROOT / "console" / "src" / "App.tsx").read_text(encoding="utf-8")
        for route in (
            "/", "/projects", "/organizations", "/notifications", "/catalog/experts",
            "/catalog/connectors", "/catalog/skills", "/catalog/knowledge", "/users",
            "/settings/catalog",
        ):
            self.assertIn(f'"{route}"', app)
        self.assertIn("ProjectDetailPage", app)
        self.assertNotIn("/legacy", app)

    def test_project_knowledge_ui_uses_central_weknora_contract(self) -> None:
        page = (ROOT / "console" / "src" / "pages" / "ProjectDetailPage.tsx").read_text(encoding="utf-8")
        self.assertIn("中央 WeKnora", page)
        self.assertIn("migrateKnowledgeBase", page)
        self.assertNotIn("Embedding-3-pro", page)
        self.assertNotIn("向量化由本地执行面完成", page)


if __name__ == "__main__":
    unittest.main()
