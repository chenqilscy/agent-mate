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
        self.old_skills_dir = settings.SKILLS_DIR
        settings.DB_PATH = Path(self.tmp.name) / "test.db"
        settings.SKILLS_DIR = Path(self.tmp.name) / "skills"
        db._local = __import__("threading").local()
        db.init_db()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        settings.SKILLS_DIR = self.old_skills_dir
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
            {"slug": "excel-csv", "name": "表格分析（运营版）", "icon": "📊", "description": "Server 描述", "instructions": "Server 指令", "version": "7", "tools": ["analyze_csv", "not-real"], "files": [{"path": "references/columns.md", "content": "# 字段"}], "category": "办公效率"},
            {"slug": "bad slug", "name": "非法项"},
        ])
        self.assertEqual({"inserted": 1, "skipped": 1}, result)
        spec = db.skill_spec_for("excel-csv")
        self.assertIsNotNone(spec)
        self.assertEqual("表格分析（运营版）", spec["name"])
        self.assertEqual("Server 指令", spec["instructions"])
        self.assertEqual("7", spec["version"])
        self.assertEqual([{"path": "references/columns.md", "content": "# 字段"}], spec["files"])
        self.assertEqual(1, len([s for s in db.skill_specs() if s["slug"] == "excel-csv"]))

        catalog = db.showcase_all()
        card = next(x for x in catalog["SK_GRID"] if x["slug"] == "excel-csv")
        self.assertEqual("办公效率", card["category"])
        self.assertEqual("表格分析（运营版）", card["name"])
        self.assertIn("办公效率", catalog["SK_CATS"])
        self.assertTrue(all(isinstance(x, dict) and x.get("slug") and x.get("category") for x in catalog["SK_GRID"]))

    def test_shared_tool_contract_matches_runtime_registry(self) -> None:
        from agent.skills import _TOOL_REGISTRY

        contract = json.loads((BACKEND.parent / "shared" / "skill-tools.json").read_text(encoding="utf-8"))
        self.assertEqual(set(_TOOL_REGISTRY), {item["name"] for item in contract})

    def test_incomplete_server_skill_is_rejected_before_downlink_insert(self) -> None:
        result = db.replace_server_skill_catalog([
            {"slug": "missing-description", "name": "不完整", "description": "", "instructions": "指令"},
            {"slug": "missing-instructions", "name": "不完整", "description": "简介", "instructions": ""},
        ])
        self.assertEqual({"inserted": 0, "skipped": 2}, result)
        self.assertIsNone(db.skill_spec_for("missing-description"))

    def test_server_recommendations_are_independent_ordered_and_scheduled(self) -> None:
        now = time.time()
        db.replace_all_downlink([
            {"category": "SKILL_RECOMMENDATIONS", "sort": 30, "data": {
                "provider": "agentmate", "skill_slug": "web-access",
                "placement": "skills.recommended", "title": "网页精选", "_enabled": True,
            }},
            {"category": "SKILL_RECOMMENDATIONS", "sort": 10, "data": {
                "provider": "skillhub", "skill_slug": "community-skill",
                "placement": "skills.recommended", "title": "社区技能", "description": "第三方商店描述",
                "icon": "✦", "category": "开发编程", "_enabled": True,
            }},
            {"category": "SKILL_RECOMMENDATIONS", "sort": 20, "data": {
                "provider": "agentmate", "skill_slug": "excel-csv",
                "placement": "skills.recommended", "ends_at": now - 1, "_enabled": True,
            }},
            {"category": "SKILL_RECOMMENDATIONS", "sort": 40, "data": {
                "provider": "agentmate", "skill_slug": "word-doc",
                "placement": "skills.recommended", "_enabled": False,
            }},
        ])

        catalog = db.showcase_all()
        self.assertEqual(["community-skill", "web-access"], [x["slug"] for x in catalog["SK_RECOMMENDATIONS"]])
        self.assertEqual("skillhub", catalog["SK_RECOMMENDATIONS"][0]["provider"])
        self.assertEqual("网页精选", catalog["SK_RECOMMENDATIONS"][1]["name"])
        self.assertEqual(["全部", "开发编程"], catalog["SK_CATS"])

    def test_empty_server_recommendation_configuration_does_not_fallback(self) -> None:
        db.replace_all_downlink([{"category": "SKILL_RECOMMENDATIONS", "sort": 0, "data": {
            "provider": "agentmate", "skill_slug": "web-access",
            "placement": "skills.recommended", "_enabled": False,
        }}])
        catalog = db.showcase_all()
        self.assertEqual([], catalog["SK_RECOMMENDATIONS"])
        self.assertEqual(["全部"], catalog["SK_CATS"])

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
        from agent import skills_store
        from agent.skills import skill_def
        self.assertIsNone(skill_def("skill-creator-guide"))
        skills_store.install_catalog_skill(
            spec["slug"], spec["name"], spec["description"], spec["instructions"]
        )
        resolved = skill_def("skill-creator-guide")
        self.assertIsNotNone(resolved)
        self.assertIn("真正创建并安装", resolved[0])
        self.assertEqual(["create_local_skill"], [tool.name for tool in resolved[1]])

    def test_catalog_skill_requires_real_install_for_content_and_runtime(self) -> None:
        from agent import skills_store
        from agent.skills import builtin_list, catalog_detail, skill_def

        detail = catalog_detail("web-access")
        self.assertIsNotNone(detail)
        self.assertTrue(detail["catalog"])
        self.assertFalse(detail["installed"])
        self.assertEqual("web-access", detail["slug"])
        self.assertEqual("AgentMate", detail["source"])
        self.assertEqual([], detail["tools"])
        self.assertEqual("", detail["body"])
        self.assertEqual("", detail["markdown"])
        self.assertEqual([], builtin_list())
        self.assertIsNone(skill_def("web-access"))

        spec = db.skill_spec_for("web-access")
        result = skills_store.install_catalog_skill(
            spec["slug"], spec["name"], spec["description"], spec["instructions"]
        )
        self.assertTrue(result["ok"])
        self.assertEqual("agentmate", result["skill"]["source"])
        self.assertTrue((settings.SKILLS_DIR / "web-access" / "SKILL.md").is_file())

        installed = catalog_detail("web-access")
        self.assertTrue(installed["installed"])
        self.assertEqual("web-access", installed["key"])
        self.assertEqual(["web_fetch"], installed["tools"])
        self.assertIn("web_fetch", installed["body"])
        self.assertEqual(["web-access"], [item["slug"] for item in builtin_list()])
        self.assertIsNotNone(skill_def("web-access"))

        self.assertTrue(skills_store.set_disabled("web-access", True))
        self.assertEqual([], builtin_list())
        self.assertIsNone(skill_def("web-access"))
        self.assertTrue(skills_store.uninstall("web-access"))
        self.assertFalse(catalog_detail("web-access")["installed"])

    def test_server_catalog_files_are_installed_to_real_skill_directory(self) -> None:
        from agent import skills_store

        db.replace_server_skill_catalog([{
            "slug": "ops-guide", "name": "运营指南", "description": "带配套文件的技能",
            "instructions": "执行前阅读 references/guide.md。", "tools": [], "category": "商业运营",
            "files": [
                {"path": "references/guide.md", "content": "# 运营检查表\n"},
                {"path": "templates/report.txt", "content": "结论：{{summary}}\n"},
            ],
        }])
        spec = db.skill_spec_for("ops-guide")
        self.assertIsNotNone(spec)
        result = skills_store.install_catalog_skill(
            spec["slug"], spec["name"], spec["description"], spec["instructions"], files=spec["files"],
        )
        self.assertTrue(result["ok"])
        root = settings.SKILLS_DIR / "ops-guide"
        self.assertTrue((root / "SKILL.md").is_file())
        self.assertEqual("# 运营检查表\n", (root / "references" / "guide.md").read_text(encoding="utf-8"))
        self.assertEqual("结论：{{summary}}\n", (root / "templates" / "report.txt").read_text(encoding="utf-8"))

    def test_catalog_upgrade_is_versioned_atomic_and_preserves_disabled_state(self) -> None:
        from agent import skills_store
        from agent.skills import catalog_detail

        db.replace_server_skill_catalog([{
            "slug": "versioned-skill", "name": "版本技能", "description": "版本升级测试",
            "instructions": "执行 v1 指令。", "version": "1", "tools": [],
            "files": [{"path": "references/version.txt", "content": "v1\n"}],
        }])
        first = db.skill_spec_for("versioned-skill")
        skills_store.install_catalog_skill(
            first["slug"], first["name"], first["description"], first["instructions"],
            first["version"], first["files"],
        )
        with self.assertRaisesRegex(skills_store.SkillImportError, "版本升级"):
            skills_store.update_skill("versioned-skill", "误编辑", "不允许", "不允许")
        self.assertTrue(skills_store.set_disabled("versioned-skill", True))
        db.replace_server_skill_catalog([{
            "slug": "versioned-skill", "name": "版本技能", "description": "版本升级测试",
            "instructions": "执行 v2 指令。", "version": "2", "tools": [],
            "files": [{"path": "references/version.txt", "content": "v2\n"}],
        }])
        pending = catalog_detail("versioned-skill")
        self.assertTrue(pending["update_available"])
        self.assertEqual("1", pending["version"])
        self.assertEqual("2", pending["catalog_version"])

        second = db.skill_spec_for("versioned-skill")
        result = skills_store.upgrade_catalog_skill(
            second["slug"], second["name"], second["description"], second["instructions"],
            second["version"], second["files"],
        )
        self.assertTrue(result["ok"])
        root = settings.SKILLS_DIR / "versioned-skill"
        self.assertTrue((root / ".disabled").is_file())
        self.assertEqual("v2\n", (root / "references" / "version.txt").read_text(encoding="utf-8"))
        self.assertIn("执行 v2 指令", (root / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse(catalog_detail("versioned-skill")["update_available"])


if __name__ == "__main__":
    unittest.main()
