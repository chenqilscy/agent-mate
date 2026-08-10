from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]


class WorkItemMobileFooterContractTest(unittest.TestCase):
    def test_execution_footer_stacks_primary_action_on_narrow_screens(self) -> None:
        component = (ROOT / "src" / "components" / "project" / "ProjectWork.tsx").read_text(encoding="utf-8")
        styles = (ROOT / "src" / "styles" / "app.css").read_text(encoding="utf-8")

        self.assertIn("wb-td-foot${executionOnly ? ' execution' : ''}", component)
        self.assertIn('className="wb-td-spacer"', component)
        media = re.search(r"@media \(max-width: 520px\)\s*\{(.+?)\n\}", styles, re.DOTALL)
        self.assertIsNotNone(media)
        rules = media.group(1)
        self.assertIn(".wb-td-foot.execution", rules)
        self.assertIn("flex-wrap: wrap", rules)
        self.assertIn("flex: 1 0 100%", rules)
        self.assertIn("min-height: 40px", rules)


if __name__ == "__main__":
    unittest.main()
