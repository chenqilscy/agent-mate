from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ConsoleAntDesignEntryTests(unittest.TestCase):
    def test_console_dependencies_are_antd6_compatible(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        dependencies = package["dependencies"]
        self.assertTrue(dependencies["antd"].startswith("^6."))
        # Pro Components stable 2.x does not declare antd 6 support; pin the compatible 3.x prerelease.
        self.assertTrue(dependencies["@ant-design/pro-components"].startswith("3."))

    def test_server_serves_new_skills_entry_and_legacy_fallback(self) -> None:
        main = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
        legacy = (ROOT / "server" / "web" / "console.html").read_text(encoding="utf-8")
        built_index = (ROOT / "server" / "web" / "console-dist" / "index.html").read_text(encoding="utf-8")

        self.assertIn('app.mount("/console-assets", StaticFiles(directory=_CONSOLE_DIST)', main)
        self.assertIn('if console_path == "catalog/skills":', main)
        self.assertIn('src="/console-assets/assets/', built_index)
        self.assertIn("const LEGACY_BASE", legacy)
        self.assertIn("REQUESTED_SKILL_SUB", legacy)

    def test_skills_page_uses_professional_management_components(self) -> None:
        page = (ROOT / "console" / "src" / "SkillsPage.tsx").read_text(encoding="utf-8")
        editor = (ROOT / "console" / "src" / "SkillEditor.tsx").read_text(encoding="utf-8")

        self.assertIn("<ProTable", page)
        self.assertIn("<PageContainer", page)
        self.assertIn("<Drawer", editor)
        self.assertIn("file-workspace", editor)


if __name__ == "__main__":
    unittest.main()
