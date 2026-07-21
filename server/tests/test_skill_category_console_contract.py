from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONSOLE = ROOT / "console" / "src"


class SkillCategoryConsoleContractTest(unittest.TestCase):
    def test_category_management_and_selectors_are_wired(self) -> None:
        page = (CONSOLE / "SkillsPage.tsx").read_text(encoding="utf-8")
        editor = (CONSOLE / "SkillEditor.tsx").read_text(encoding="utf-8")
        manager = (CONSOLE / "SkillCategories.tsx").read_text(encoding="utf-8")
        for marker in ("分类管理", "<SkillCategories", '"SKILL_CATEGORIES"', "categories={skillCategories}"):
            self.assertIn(marker, page)
        self.assertIn('name="category_slug"', editor)
        self.assertIn("选择已管理的分类", editor)
        for marker in ("新增分类", "updateCatalogItem", "deleteCatalogItem", "分类状态"):
            self.assertIn(marker, manager)


if __name__ == "__main__":
    unittest.main()
