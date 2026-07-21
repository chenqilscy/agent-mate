"""Dedicated office-file tools and first golden validators (WB-243)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import office, tools  # noqa: E402
from agent.sandbox import use_root  # noqa: E402


class OfficeArtifactToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        use_root(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_docx_report_reopens_with_headings_and_table(self) -> None:
        result = tools.safe_run("create_docx", {
            "path": "report.docx", "title": "Quarterly Report",
            "sections": [{"heading": "Summary", "paragraphs": ["Revenue grew."]}],
            "tables": [{"rows": [["Metric", "Value"], ["Revenue", 42]]}],
        })
        self.assertEqual(1, len(result.artifacts), result.text)
        check = office.inspect_office_file("report.docx")
        self.assertTrue(check["valid"])
        self.assertGreaterEqual(check["headings"], 1)
        self.assertEqual(1, check["tables"])

    def test_xlsx_reopens_with_formula_chart_and_recalculation(self) -> None:
        result = tools.safe_run("create_xlsx", {
            "path": "analysis.xlsx", "sheets": [{
                "name": "Data", "rows": [["Month", "Value"], ["Jan", 10], ["Feb", 20]],
                "formulas": [{"cell": "B4", "formula": "=SUM(B2:B3)"}],
                "chart": {"type": "bar", "title": "Monthly", "data_min_col": 2,
                          "data_max_col": 2, "categories_col": 1, "min_row": 1, "max_row": 3},
            }],
        })
        self.assertEqual(1, len(result.artifacts), result.text)
        check = office.inspect_office_file("analysis.xlsx")
        self.assertEqual(1, check["formulas"])
        self.assertEqual(1, check["charts"])
        self.assertTrue(check["recalculation_on_open"])

    def test_pptx_reopens_and_all_shapes_stay_in_slide_bounds(self) -> None:
        result = tools.safe_run("create_pptx", {
            "path": "deck.pptx", "slides": [
                {"title": "AgentMate", "bullets": ["Delivery first"]},
                {"title": "Evidence", "bullets": ["Real file", "Real validation"]},
            ],
        })
        self.assertEqual(1, len(result.artifacts), result.text)
        check = office.inspect_office_file("deck.pptx")
        self.assertEqual(2, check["slides"])
        self.assertEqual([], check["bounds_violations"])

    def test_pdf_reopens_with_page_and_extractable_text(self) -> None:
        result = tools.safe_run("create_pdf", {
            "path": "package.pdf", "title": "Delivery Package",
            "paragraphs": ["Verified local PDF output."],
            "tables": [{"rows": [["Check", "Result"], ["Hash", "Pass"]]}],
        })
        self.assertEqual(1, len(result.artifacts), result.text)
        check = office.inspect_office_file("package.pdf")
        self.assertGreaterEqual(check["pages"], 1)
        self.assertGreater(check["extractable_characters"], 0)

    def test_writers_are_not_plan_safe_but_inspection_is(self) -> None:
        plan_names = {tool.name for tool in tools.base_tools(plan=True)}
        self.assertIn("inspect_office_file", plan_names)
        for name in ("create_docx", "create_xlsx", "create_pptx", "create_pdf"):
            self.assertNotIn(name, plan_names)

    def test_bad_extension_leaves_no_partial_file(self) -> None:
        result = tools.safe_run("create_docx", {
            "path": "wrong.pdf", "title": "No", "sections": [],
        })
        self.assertIn("工具出错", result.text)
        self.assertFalse((self.root / "wrong.pdf").exists())
        self.assertEqual([], list(self.root.glob(".*.tmp*")))

    def test_ten_golden_task_identities_are_stable_and_unique(self) -> None:
        tasks = json.loads((BACKEND / "tests" / "golden" / "tasks.json").read_text(encoding="utf-8"))
        self.assertEqual([f"G{i:02d}" for i in range(1, 11)], [task["id"] for task in tasks])
        self.assertEqual(10, len({task["validator"] for task in tasks}))
        self.assertTrue(all(task["required"] for task in tasks))


if __name__ == "__main__":
    unittest.main()
