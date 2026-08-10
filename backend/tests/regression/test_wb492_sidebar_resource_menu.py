from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class SidebarResourceMenuContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sidebar = (ROOT / "src/components/layout/Sidebar.tsx").read_text(
            encoding="utf-8"
        )
        self.styles = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")

    def test_resource_menu_is_a_right_anchored_flyout(self) -> None:
        self.assertIn("placement={navOpen ? 'bottomLeft' : 'rightTop'}", self.sidebar)
        self.assertIn("classNames={{ root: 'resource-menu-popup' }}", self.sidebar)

    def test_all_resource_entries_have_bounded_icons(self) -> None:
        self.assertIn("key: 'myfiles', icon: <IcFolder />", self.sidebar)
        for key in ("kdocs", "knowledge", "inspire"):
            self.assertRegex(
                self.sidebar,
                rf"key: '{key}', icon: <svg[^>]*width=\"16\"",
            )
        self.assertIn(
            ".resource-menu-popup .ant-dropdown-menu-item-icon", self.styles
        )
        self.assertIn("width: 16px !important", self.styles)
        self.assertIn("height: 16px !important", self.styles)


if __name__ == "__main__":
    unittest.main()
