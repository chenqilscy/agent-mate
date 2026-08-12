"""WB-535: retained Desktop Home actions meet the narrow-screen touch baseline."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class MobileHomeTouchTargetsTest(unittest.TestCase):
    def test_narrow_breakpoint_expands_retained_home_actions(self) -> None:
        css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")
        mobile = css[css.rindex("@media (max-width: 640px)") :]
        self.assertRegex(mobile, r"\.shell-nav-toggle\s*\{\s*width:\s*44px")
        selector_group = mobile[mobile.index(".home-login-card .btn-dark") :]
        rule = selector_group[: selector_group.index("}") + 1]
        for selector in (
            ".home-login-card .btn-dark",
            ".home-refresh.ant-btn",
            ".home-data-warning-action.ant-btn",
            ".home-console-action.ant-btn",
        ):
            self.assertIn(selector, rule)
        self.assertRegex(rule, r"min-height:\s*44px")


if __name__ == "__main__":
    unittest.main()
