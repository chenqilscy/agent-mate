"""Context authority ordering regression coverage (WB-406)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.context_layers import CONFLICT_RULE, ContextLayers  # noqa: E402


class ContextLayersTest(unittest.TestCase):
    def test_renders_authority_order_and_omits_empty_layers(self) -> None:
        layers = ContextLayers("系统安全")
        layers.add("skill", "技能流程", source="skill:a", authority="procedure", priority=700, heading="Skill")
        layers.add("empty", "  ", source="none", authority="history", priority=400)
        layers.add("project", "项目规范", source="project:p", authority="project", priority=100, heading="项目")
        layers.add("peer", "同级一", source="one", authority="advice", priority=600)
        layers.add("peer_two", "同级二", source="two", authority="advice", priority=600)

        rendered = layers.render()
        self.assertIn(CONFLICT_RULE, rendered)
        self.assertLess(rendered.index("项目规范"), rendered.index("同级一"))
        self.assertLess(rendered.index("同级一"), rendered.index("同级二"))
        self.assertLess(rendered.index("同级二"), rendered.index("技能流程"))
        self.assertNotIn("empty", str(layers.manifest()))

        self.assertEqual(
            ["system_core", "precedence", "project", "peer", "peer_two", "skill"],
            [item["key"] for item in layers.manifest()],
        )


if __name__ == "__main__":
    unittest.main()
