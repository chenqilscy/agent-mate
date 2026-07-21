import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"


class AppAntDesignMigrationTests(unittest.TestCase):
    def test_versions_are_pinned(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        dependencies = package["dependencies"]
        self.assertEqual(dependencies["antd"], "6.5.1")
        self.assertEqual(dependencies["@ant-design/pro-components"], "3.1.14-2")

    def test_app_is_owned_by_ant_theme_and_pro_page_shell(self) -> None:
        main = (SRC / "main.tsx").read_text(encoding="utf-8")
        app = (SRC / "App.tsx").read_text(encoding="utf-8")
        provider = (SRC / "components/ui/AppThemeProvider.tsx").read_text(encoding="utf-8")
        self.assertIn("<AppThemeProvider>", main)
        self.assertIn("<ProLayout", app)
        self.assertIn("<PageContainer", app)
        self.assertIn("<ConfigProvider", provider)
        self.assertIn("darkAlgorithm", provider)

    def test_visible_native_form_controls_use_ant_primitives(self) -> None:
        primitive = SRC / "components/ui/Primitives.tsx"
        violations: list[str] = []
        pattern = re.compile(r"<(?:button|input|select|textarea)\b")
        for path in SRC.rglob("*.tsx"):
            if path == primitive:
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_all_product_modals_use_ant_modal_bridge(self) -> None:
        sources = "\n".join(path.read_text(encoding="utf-8") for path in SRC.rglob("*.tsx"))
        bridge = (SRC / "components/ui/AntModalBridge.tsx").read_text(encoding="utf-8")
        self.assertNotIn("np-overlay open", sources)
        self.assertGreaterEqual(sources.count("<AntModalBridge"), 16)
        self.assertIn("mask={{ closable: closeOnMask }}", bridge)
        self.assertNotIn("maskClosable=", bridge)


if __name__ == "__main__":
    unittest.main()
