from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RecentExecutionSelectionLatencyContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sidebar = (ROOT / "src" / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")

    def test_live_session_precedes_the_route_hydration_fallback(self) -> None:
        live_session = self.sidebar.index("? activeSessionId : null")
        route_fallback = self.sidebar.index("?? route.sessionId ?? null")
        self.assertLess(live_session, route_fallback)
        self.assertNotIn("const selectedSessionId = route.sessionId", self.sidebar)

    def test_selection_does_not_depend_on_a_timer_or_session_poll(self) -> None:
        selection_start = self.sidebar.index("const selectedSessionId = (")
        selection_end = self.sidebar.index("useEffect", selection_start)
        selection = self.sidebar[selection_start:selection_end]
        self.assertNotIn("setTimeout", selection)
        self.assertNotIn("loadSessions", selection)


if __name__ == "__main__":
    unittest.main()
