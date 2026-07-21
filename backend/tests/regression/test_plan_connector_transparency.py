"""Plan connector loadout transparency coverage (WB-273)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.runtime import connector_mode_skips  # noqa: E402


class PlanConnectorTransparencyTest(unittest.TestCase):
    def test_plan_reports_every_selected_connector_as_not_loaded(self) -> None:
        self.assertEqual(
            [
                {"name": "GitHub", "reason": "计划模式不启用外部连接器"},
                {"name": "Notes", "reason": "计划模式不启用外部连接器"},
            ],
            connector_mode_skips(["GitHub", "Notes"], plan=True, ask=False),
        )

    def test_exec_does_not_create_mode_skip_entries(self) -> None:
        self.assertEqual([], connector_mode_skips(["GitHub"], plan=False, ask=False))


if __name__ == "__main__":
    unittest.main()
