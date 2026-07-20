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

    def test_server_catalog_overrides_by_slug_and_drives_categories(self) -> None:
        result = db.replace_server_skill_catalog([
            {"slug": "excel-csv", "name": "表格分析（运营版）", "icon": "📊", "description": "Server 描述", "instructions": "Server 指令", "tools": ["analyze_csv", "not-real"], "category": "办公效率"},
            {"slug": "bad slug", "name": "非法项"},
        ])
        self.assertEqual({"inserted": 1, "skipped": 1}, result)
        spec = db.skill_spec_for("excel-csv")
        self.assertIsNotNone(spec)
        self.assertEqual("表格分析（运营版）", spec["name"])
        self.assertEqual("Server 指令", spec["instructions"])
        self.assertEqual(1, len([s for s in db.skill_specs() if s["slug"] == "excel-csv"]))

        catalog = db.showcase_all()
        card = next(x for x in catalog["SK_GRID"] if x["slug"] == "excel-csv")
        self.assertEqual("办公效率", card["category"])
        self.assertEqual("表格分析（运营版）", card["name"])
        self.assertIn("办公效率", catalog["SK_CATS"])
        self.assertTrue(all(isinstance(x, dict) and x.get("slug") and x.get("category") for x in catalog["SK_GRID"]))

    def test_existing_creator_guide_seed_migrates_to_real_create_tool(self) -> None:
        old_instruction = "当用户想创建自定义技能时，说明技能 = 提示词 + 工具包 的结构，并给出可落地的模板。"
        conn = db.get_conn()
        conn.execute(
            "UPDATE catalog_skills SET instructions=?, tools='[]' "
            "WHERE scope='builtin' AND slug='skill-creator-guide'",
            (old_instruction,),
        )
        conn.commit()
        db._migrate_columns()

        spec = db.skill_spec_for("skill-creator-guide")
        self.assertIsNotNone(spec)
        self.assertEqual(["create_local_skill"], spec["tools"])
        from agent.skills import skill_def
        resolved = skill_def("skill-creator-guide")
        self.assertIsNotNone(resolved)
        self.assertIn("真正创建并安装", resolved[0])
        self.assertEqual(["create_local_skill"], [tool.name for tool in resolved[1]])


if __name__ == "__main__":
    unittest.main()
