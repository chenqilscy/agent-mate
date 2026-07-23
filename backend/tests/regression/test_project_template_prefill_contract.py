from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ProjectTemplatePrefillContractTests(unittest.TestCase):
    def test_every_project_card_has_a_new_project_template(self) -> None:
        catalog = (ROOT / "src" / "data" / "catalog.ts").read_text(encoding="utf-8")
        cards_source = catalog.split("export const PROJ_TPL", 1)[1].split("export const EXP_SCENES", 1)[0]
        templates_source = catalog.split("export const NP_TPLS", 1)[1]
        card_names = re.findall(r"\['[^']+', '([^']+)',", cards_source)
        template_names = set(re.findall(r"^\s*\['([^']+)', `", templates_source, re.MULTILINE))

        self.assertEqual(5, len(card_names))
        self.assertEqual([], [name for name in card_names if name not in template_names])

    def test_selected_template_is_forwarded_and_reset(self) -> None:
        projects = (ROOT / "src" / "views" / "ProjectsView.tsx").read_text(encoding="utf-8")
        modal = (ROOT / "src" / "components" / "project" / "NewProjectModal.tsx").read_text(encoding="utf-8")

        self.assertIn("const [selectedTemplate, setSelectedTemplate]", projects)
        self.assertIn("onClick={() => openNewProject(n)}", projects)
        self.assertIn("initialTemplate={selectedTemplate}", projects)
        self.assertIn("setSelectedTemplate(null)", projects)
        self.assertIn("initialTemplate = null", modal)
        self.assertIn("if (!initialTemplate) return", modal)
        self.assertIn("item[0] === initialTemplate", modal)
        self.assertIn("setTplLabel(template[0])", modal)
        self.assertIn("setInstruction(template[1])", modal)
        self.assertIn("conn: new Set(template[2])", modal)
        self.assertIn("exp: new Set(template[3])", modal)


if __name__ == "__main__":
    unittest.main()
