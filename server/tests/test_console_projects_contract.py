"""WB-307: the project instruction column must read the row's raw field."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ConsoleProjectsContractTest(unittest.TestCase):
    def test_instruction_renderer_uses_row_data_not_protable_rendered_value(self) -> None:
        source = (ROOT / "console" / "src" / "pages" / "ProjectsPage.tsx").read_text(
            encoding="utf-8"
        )
        column = re.search(
            r'title: "说明",(?P<body>.*?)\n\s*},\n\s*{\n\s*title: "角色"',
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(column)
        body = column.group("body")
        self.assertIn("render: (_value, item)", body)
        self.assertIn("item.instruction", body)
        self.assertNotIn("String(value", body)
        self.assertIn("未设置项目指令", body)


if __name__ == "__main__":
    unittest.main()
