from pathlib import Path
import json
import re
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from storage import db  # noqa: E402


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
        self.assertIn("skill: new Set(readyTemplateSkills(template[4] ?? []))", modal)
        self.assertIn("if (skill.disabled) continue", modal)

    def test_templates_include_only_real_builtin_skill_defaults(self) -> None:
        showcase = json.loads(
            (ROOT / "backend" / "storage" / "catalog_showcase.json").read_text(encoding="utf-8")
        )
        seed = (ROOT / "backend" / "storage" / "catalog_seed.py").read_text(encoding="utf-8")
        builtin_skill_slugs = set(re.findall(r'\{"slug": "([^"]+)", "name":', seed))

        templates = showcase["NP_TPLS"]
        self.assertEqual(6, len(templates))
        for template in templates:
            self.assertEqual(5, len(template), template[0])
            self.assertLessEqual(set(template[4]), builtin_skill_slugs, template[0])

    def test_name_limit_counter_and_two_column_layout_are_wired(self) -> None:
        modal = (ROOT / "src" / "components" / "project" / "NewProjectModal.tsx").read_text(encoding="utf-8")
        projects = (ROOT / "src" / "views" / "ProjectsView.tsx").read_text(encoding="utf-8")
        styles = (ROOT / "src" / "styles" / "app.css").read_text(encoding="utf-8")

        self.assertIn("const PROJECT_NAME_MAX = 15", modal)
        self.assertIn("maxLength={PROJECT_NAME_MAX}", modal)
        self.assertIn("name.length}/{PROJECT_NAME_MAX}", modal)
        self.assertIn('className="card-grid project-template-grid"', projects)
        self.assertIn(".project-template-grid { grid-template-columns: repeat(2", styles)


class ProjectTemplateMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        db._local = threading.local()
        db.init_db()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_legacy_default_is_upgraded_but_operator_edit_is_preserved(self) -> None:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT id FROM catalog_showcase WHERE kind='NP_TPLS' "
            "AND json_extract(data, '$[0]')='自定义'"
        ).fetchone()
        self.assertIsNotNone(row)

        legacy = ["自定义", "", [], []]
        conn.execute(
            "UPDATE catalog_showcase SET data=? WHERE id=?",
            (json.dumps(legacy, ensure_ascii=False), row["id"]),
        )
        conn.commit()
        db._migrate_project_template_defaults()
        migrated = json.loads(conn.execute(
            "SELECT data FROM catalog_showcase WHERE id=?", (row["id"],)
        ).fetchone()["data"])
        self.assertEqual(["自定义", "", [], [], []], migrated)

        edited = ["自定义", "运营者自己的指令", [], []]
        conn.execute(
            "UPDATE catalog_showcase SET data=? WHERE id=?",
            (json.dumps(edited, ensure_ascii=False), row["id"]),
        )
        conn.commit()
        db._migrate_project_template_defaults()
        preserved = json.loads(conn.execute(
            "SELECT data FROM catalog_showcase WHERE id=?", (row["id"],)
        ).fetchone()["data"])
        self.assertEqual(edited, preserved)


if __name__ == "__main__":
    unittest.main()
