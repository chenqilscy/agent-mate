from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "console" / "src" / "components" / "project" / "ProjectWorkspace.tsx"


class CustomFieldOptionEditorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKSPACE.read_text(encoding="utf-8")

    def test_select_fields_use_an_explicit_option_editor(self) -> None:
        field_modal = self.source.split(
            'title={editingField ? "编辑自定义字段" : "新增自定义字段"}', 1
        )[1].split(
            'title={editingSprint ? "编辑 Sprint" : "新建 Sprint"}', 1
        )[0]
        self.assertIn("function CustomFieldOptionEditor", self.source)
        self.assertIn('aria-label="选项名称"', self.source)
        self.assertIn('placeholder="输入选项，按 Enter 或点击添加"', self.source)
        self.assertIn("已添加 ${options.length}/50", self.source)
        self.assertIn("<CustomFieldOptionEditor />", field_modal)
        self.assertNotIn('mode="tags"', field_modal)

    def test_select_field_submission_is_validated_and_non_select_options_are_cleared(self) -> None:
        self.assertIn('new Error("请至少添加一个选项")', self.source)
        self.assertIn('values.field_type === "select" ? values.options || [] : []', self.source)
        self.assertIn('setError("最多添加 50 个选项")', self.source)
        self.assertIn("candidate.length > 80", self.source)


if __name__ == "__main__":
    unittest.main()
