"""WB-487: retired solution paths remain resolvable without regaining authority."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RETIRED = (
    "agentmate-实现方案.md",
    "agentmate-server-架构设计.md",
    "agentmate-功能规划-v2.md",
    "agentmate-助理-架构设计.md",
    "agentmate-能力完成度评估-2026-07-22.md",
)


class RetiredDocumentLinksTest(unittest.TestCase):
    def test_retired_paths_are_redirect_pages(self) -> None:
        for name in RETIRED:
            path = ROOT / "docs" / name
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            self.assertIn("状态：", text, name)
            self.assertTrue("退役" in text or "历史" in text, name)

    def test_project_guide_points_to_current_authority(self) -> None:
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("docs/README.md", text)
        self.assertIn("docs/agentmate-server-first-架构设计.md", text)
        self.assertNotIn("](docs/agentmate-实现方案.md)", text)
        self.assertNotIn("](docs/agentmate-server-架构设计.md)", text)


if __name__ == "__main__":
    unittest.main()
