from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RecentExecutionActiveStateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sidebar = (ROOT / "src" / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")
        self.styles = (ROOT / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    def test_current_run_is_derived_from_route_with_store_fallback(self) -> None:
        self.assertIn("const activeSessionId = useChatStore((s) => s.activeId)", self.sidebar)
        self.assertIn("const selectedSessionId = route.sessionId", self.sidebar)
        self.assertIn("view === 'chat' || view === 'projexec'", self.sidebar)

    def test_current_run_has_persistent_visual_and_semantic_state(self) -> None:
        self.assertIn("selectedSessionId === session.id ? 'active' : ''", self.sidebar)
        self.assertIn("aria-current={selectedSessionId === session.id ? 'page' : undefined}", self.sidebar)
        self.assertIn(".sb-run.active", self.styles)
        self.assertIn("background: var(--brand-soft)", self.styles)
        self.assertIn("box-shadow: inset 2px 0 0 var(--brand)", self.styles)


if __name__ == "__main__":
    unittest.main()
