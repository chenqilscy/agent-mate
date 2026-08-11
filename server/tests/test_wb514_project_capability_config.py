from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "console" / "src" / "pages" / "ProjectDetailPage.tsx"
STYLES = ROOT / "console" / "src" / "styles.css"


class ProjectCapabilityConfigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.styles = STYLES.read_text(encoding="utf-8")

    def test_catalog_metadata_is_preserved_in_a_searchable_picker(self) -> None:
        self.assertIn("function mapProjectCapabilityOptions", self.page)
        self.assertIn("function ProjectCapabilityPicker", self.page)
        self.assertIn("option.description", self.page)
        self.assertIn("option.tags.map", self.page)
        self.assertIn('aria-pressed={active}', self.page)
        self.assertIn("没有匹配的能力", self.page)

    def test_configuration_explains_operational_and_historical_boundaries(self) -> None:
        self.assertIn("连接器在目录中可选不代表设备已经就绪", self.page)
        self.assertIn("个历史能力已不在当前目录", self.page)
        self.assertIn("归档项目的能力配置只读", self.page)
        self.assertIn("有未保存变更", self.page)
        self.assertIn('description="正在加载能力目录…"', self.page)
        self.assertNotIn('tip="正在加载能力目录…"', self.page)
        self.assertIn('onNavigateKnowledge={() => selectProjectTab("knowledge")}', self.page)

    def test_existing_project_patch_contract_and_responsive_states_remain_explicit(self) -> None:
        self.assertIn("await consoleApi.updateProject(project.id, values)", self.page)
        self.assertIn('name="instruction"', self.page)
        self.assertIn('name="connectors"', self.page)
        self.assertIn('name="experts"', self.page)
        self.assertIn('name="skills"', self.page)
        self.assertIn(".project-capability-option.is-selected", self.styles)
        self.assertIn(".project-capability-summary { grid-template-columns: repeat(2", self.styles)
        self.assertIn(".project-capability-grid { grid-template-columns: 1fr", self.styles)


if __name__ == "__main__":
    unittest.main()
