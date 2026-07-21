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

        icon_picker = (SRC / "components/ui/IconPicker.tsx").read_text(encoding="utf-8")
        icon_picker_css = (SRC / "styles/icon-picker.css").read_text(encoding="utf-8")
        self.assertIn('<Button\n                    type="text"', icon_picker)
        self.assertIn(".icon-picker-option.ant-btn", icon_picker_css)

    def test_all_product_modals_use_ant_modal_bridge(self) -> None:
        sources = "\n".join(path.read_text(encoding="utf-8") for path in SRC.rglob("*.tsx"))
        bridge = (SRC / "components/ui/AntModalBridge.tsx").read_text(encoding="utf-8")
        self.assertNotIn("np-overlay open", sources)
        self.assertGreaterEqual(sources.count("<AntModalBridge"), 16)
        self.assertIn("mask={{ closable: closeOnMask }}", bridge)
        self.assertNotIn("maskClosable=", bridge)

    def test_settings_center_uses_mobile_navigation_instead_of_squeezed_columns(self) -> None:
        settings = (SRC / "components/settings/SettingsModal.tsx").read_text(encoding="utf-8")
        css = (SRC / "styles/app.css").read_text(encoding="utf-8")
        self.assertIn('className="set-mobile-nav"', settings)
        self.assertIn('aria-label="设置页面"', settings)
        self.assertIn(".set-mobile-nav { display: none; }", css)
        self.assertIn(".set-layout { flex-direction: column; }", css)
        self.assertIn(".set-nav-menu { display: none; }", css)
        self.assertIn(".set-style { height: auto; min-height: 58px;", css)
        self.assertIn("white-space: normal;", css)

    def test_borderless_product_buttons_keep_zero_width_border_on_hover(self) -> None:
        primitive = (SRC / "components/ui/Primitives.tsx").read_text(encoding="utf-8")
        marker = re.search(
            r"const BORDERLESS_VISUAL_CLASSES = new Set\(\[(.*?)\]\)",
            primitive,
            re.DOTALL,
        )
        asymmetric_marker = re.search(
            r"const ASYMMETRIC_VISUAL_CLASSES = new Set\(\[(.*?)\]\)",
            primitive,
            re.DOTALL,
        )
        self.assertIsNotNone(marker)
        self.assertIsNotNone(asymmetric_marker)
        configured = set(re.findall(r"'([A-Za-z_][\w-]*)'", marker.group(1)))
        configured.update(re.findall(r"'([A-Za-z_][\w-]*)'", asymmetric_marker.group(1)))

        button_classes: set[str] = set()
        class_attr = re.compile(
            r"<WbButton\b[\s\S]{0,240}?className\s*=\s*(?:\"([^\"]+)\"|\{([^}\n]+)\})"
        )
        for path in SRC.rglob("*.tsx"):
            source = path.read_text(encoding="utf-8")
            for match in class_attr.finditer(source):
                value = match.group(1) or match.group(2) or ""
                for literal in re.findall(r"['\"`]([^'\"`]+)['\"`]", value):
                    button_classes.update(literal.split())
                if match.group(1):
                    button_classes.update(match.group(1).split())

        css = "\n".join(path.read_text(encoding="utf-8") for path in (SRC / "styles").glob("*.css"))
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        borderless_used: set[str] = set()
        implicit_borderless_selectors: list[str] = []
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css, re.DOTALL):
            if not re.search(r"(?:^|;)\s*border\s*:\s*(?:none|0(?:px)?)\s*(?:;|$)", body):
                continue
            if re.search(r"(?:^|[\s>+~,])button(?=[:.#\s,]|$)", selectors):
                implicit_borderless_selectors.append(" ".join(selectors.split()))
            for class_name in re.findall(r"\.([A-Za-z_][\w-]*)", selectors):
                if class_name in button_classes:
                    borderless_used.add(class_name)

        self.assertEqual(implicit_borderless_selectors, [])
        self.assertTrue(borderless_used.issubset(configured))
        self.assertEqual(configured - {"shell-nav-toggle"}, borderless_used)
        integration = (SRC / "styles/antd.css").read_text(encoding="utf-8")
        self.assertIn(".ant-btn.wb-button-borderless", integration)
        self.assertIn(".ant-btn.shell-nav-toggle", integration)
        self.assertIn(".ant-btn.asst-seg-btn", integration)


if __name__ == "__main__":
    unittest.main()
