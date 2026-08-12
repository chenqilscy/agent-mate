import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class DesktopSurfaceRetirementContractTests(unittest.TestCase):
    def test_unroutable_business_views_are_removed_from_the_product_bundle(self) -> None:
        app = source("src/App.tsx")
        router = source("src/lib/router.ts")
        for relative in (
            "src/views/AssistantView.tsx",
            "src/views/InspireView.tsx",
            "src/views/KdocsView.tsx",
            "src/views/ProjectHomeView.tsx",
            "src/components/channel/AssistantChat.tsx",
            "src/components/project/ProjectTaskCenter.tsx",
            "src/components/server/ServerCommentsPanel.tsx",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)
        for retired in ("AssistantView", "InspireView", "KdocsView", "ProjectHomeView"):
            self.assertNotIn(retired, app)
        for retired_route in ("'/inspiration'", "'/files'", "'/kdocs'", "|| 'new'"):
            self.assertNotIn(retired_route, router)

    def test_settings_navigation_contains_only_real_pages(self) -> None:
        settings = source("src/components/settings/SettingsModal.tsx")
        store = source("src/stores/uiStore.ts")
        for placeholder in ("shortcuts", "help", "assistant", "Soon", "即将上线", "提交反馈", "查看帮助文档"):
            self.assertNotIn(placeholder, settings)
        for retired_id in ("'shortcuts'", "'help'", "'assistant'"):
            self.assertNotIn(retired_id, store)
        for real_id in ("account", "system", "runtime", "diagnostics", "model", "memory", "data", "security"):
            self.assertIn(f"id: '{real_id}'", settings)


if __name__ == "__main__":
    unittest.main()
