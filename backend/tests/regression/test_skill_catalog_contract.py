"""Offline regression gate for the skill identity/catalog contract (WB-204)."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from storage import db  # noqa: E402


class SkillCatalogContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "test.db"
        db._local = __import__("threading").local()
        db.init_db()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = __import__("threading").local()
        self.tmp.cleanup()

    def test_legacy_names_migrate_to_slugs_idempotently(self) -> None:
        now = time.time()
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO projects (id,name,owner_id,skills,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            ("p1", "legacy", "local-user", json.dumps(["Web Access（浏览器自动化）", "excel-csv", "腾讯自选股"]), now, now),
        )
        conn.execute(
            "INSERT INTO assistants (id,owner_id,name,skills,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            ("a1", "local-user", "legacy", json.dumps(["Excel 文件处理", "word-doc"]), now, now),
        )
        conn.commit()

        from agent.skills import canonical_skill_key
        first = db.migrate_skill_identities(canonical_skill_key)
        self.assertEqual({"changed": 2, "dropped": 1}, first)
        self.assertEqual(["web-access", "excel-csv"], json.loads(conn.execute("SELECT skills FROM projects WHERE id='p1'").fetchone()[0]))
        self.assertEqual(["excel-csv", "word-doc"], json.loads(conn.execute("SELECT skills FROM assistants WHERE id='a1'").fetchone()[0]))
        self.assertEqual({"changed": 0, "dropped": 0}, db.migrate_skill_identities(canonical_skill_key))

    def test_hub_catalog_overrides_by_slug_and_drives_categories(self) -> None:
        result = db.replace_hub_skill_catalog([
            {"slug": "excel-csv", "name": "表格分析（运营版）", "icon": "📊", "description": "Hub 描述", "instructions": "Hub 指令", "tools": ["analyze_csv", "not-real"], "category": "办公效率"},
            {"slug": "bad slug", "name": "非法项"},
        ])
        self.assertEqual({"inserted": 1, "skipped": 1}, result)
        spec = db.skill_spec_for("excel-csv")
        self.assertIsNotNone(spec)
        self.assertEqual("表格分析（运营版）", spec["name"])
        self.assertEqual("Hub 指令", spec["instructions"])
        self.assertEqual(1, len([s for s in db.skill_specs() if s["slug"] == "excel-csv"]))

        catalog = db.showcase_all()
        card = next(x for x in catalog["SK_GRID"] if x["slug"] == "excel-csv")
        self.assertEqual("办公效率", card["category"])
        self.assertEqual("表格分析（运营版）", card["name"])
        self.assertIn("办公效率", catalog["SK_CATS"])
        self.assertTrue(all(isinstance(x, dict) and x.get("slug") and x.get("category") for x in catalog["SK_GRID"]))


if __name__ == "__main__":
    unittest.main()
