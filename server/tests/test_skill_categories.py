"""Server 权威 Skill 分类目录回归（WB-267）。"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers.catalog import (  # noqa: E402
    CatalogItemBody, UpdateItemBody, _normalize_skill_recommendation,
    _validate_app_skill, _validate_skill_recommendation, create_item, delete_item,
    list_catalog, update_item,
)


class SkillCategoryContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.admin = SimpleNamespace(id="admin", is_platform_admin=True)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_bootstrap_migrates_categories_and_skill_references(self) -> None:
        categories = list_catalog("SKILL_CATEGORIES", True, self.admin)["items"]
        self.assertEqual(
            ["development", "content", "office", "data", "business", "other"],
            [item["data"]["slug"] for item in categories],
        )
        skills = list_catalog("APP_SKILLS", True, self.admin)["items"]
        self.assertTrue(all(item["data"].get("category_slug") for item in skills))
        self.assertEqual("开发编程", next(
            item["data"]["category"] for item in skills if item["data"]["slug"] == "web-access"
        ))
        db.init_db()
        self.assertEqual(6, len(list_catalog("SKILL_CATEGORIES", True, self.admin)["items"]))

    def test_legacy_free_text_category_migrates_idempotently(self) -> None:
        conn = db.get_conn()
        row = next(
            item for item in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True)
            if item["data"]["slug"] == "web-access"
        )
        legacy = dict(row["data"])
        legacy.pop("category_slug", None)
        legacy["category"] = "专项研究"
        conn.execute("DELETE FROM catalog_items WHERE category='SKILL_CATEGORIES'")
        conn.execute("DELETE FROM settings WHERE k='skill_categories_v1'")
        conn.execute("UPDATE catalog_items SET data=? WHERE id=?", (json.dumps(legacy, ensure_ascii=False), row["id"]))
        conn.commit()

        db.init_db()
        categories = list_catalog("SKILL_CATEGORIES", True, self.admin)["items"]
        migrated = next(item for item in categories if item["data"]["name"] == "专项研究")
        self.assertTrue(migrated["data"]["slug"].startswith("legacy-"))
        skill = next(
            item for item in list_catalog("APP_SKILLS", True, self.admin)["items"]
            if item["data"]["slug"] == "web-access"
        )
        self.assertEqual(migrated["data"]["slug"], skill["data"]["category_slug"])
        db.init_db()
        self.assertEqual(7, len(list_catalog("SKILL_CATEGORIES", True, self.admin)["items"]))

    def test_category_crud_rename_and_reference_delete_guard(self) -> None:
        category_id = create_item(CatalogItemBody(
            category="SKILL_CATEGORIES",
            data={"slug": "research", "name": "研究分析", "icon": "🔬", "description": "研究类"},
            sort=70,
        ), self.admin)["id"]
        skill_id = db.create_catalog_item(category="APP_SKILLS", data={
            "slug": "researcher", "name": "研究员", "icon": "🔬",
            "category_slug": "research", "category": "研究分析",
            "description": "执行研究", "instructions": "执行真实研究。", "tools": [], "files": [],
        })
        update_item(category_id, UpdateItemBody(data={
            "slug": "research", "name": "深度研究", "icon": "🔬", "description": "研究类",
        }), self.admin)
        skills = list_catalog("APP_SKILLS", True, self.admin)["items"]
        renamed = next(item for item in skills if item["id"] == skill_id)
        self.assertEqual("深度研究", renamed["data"]["category"])
        with self.assertRaisesRegex(HTTPException, "still referenced"):
            delete_item(category_id, self.admin)

    def test_disabled_category_rejects_new_binding_and_recommendation_inherits(self) -> None:
        recommendation = {
            "provider": "skillhub", "skill_slug": "external-office",
            "placement": "skills.recommended", "title": "外部办公技能",
            "description": "办公推荐", "category_slug": "office",
        }
        recommendation_id = create_item(CatalogItemBody(
            category="SKILL_RECOMMENDATIONS", data=recommendation,
        ), self.admin)["id"]
        office = next(
            item for item in list_catalog("SKILL_CATEGORIES", True, self.admin)["items"]
            if item["data"]["slug"] == "office"
        )
        update_item(office["id"], UpdateItemBody(enabled=False), self.admin)
        with self.assertRaisesRegex(HTTPException, "disabled"):
            _validate_app_skill({
                "slug": "new-office", "name": "新办公技能", "category_slug": "office",
                "description": "办公", "instructions": "处理办公任务。", "tools": [], "files": [],
            })
        with self.assertRaisesRegex(HTTPException, "disabled"):
            _validate_skill_recommendation({
                **recommendation, "skill_slug": "another-office",
            })
        update_item(recommendation_id, UpdateItemBody(data={
            **recommendation, "title": "更新后的外部办公技能",
        }), self.admin)
        inherited = _normalize_skill_recommendation({
            "provider": "agentmate", "skill_slug": "web-access", "placement": "skills.recommended",
        })
        self.assertEqual("development", inherited["category_slug"])
        self.assertEqual("开发编程", inherited["category"])

    def test_duplicate_slug_and_name_are_rejected(self) -> None:
        with self.assertRaisesRegex(HTTPException, "slug already exists"):
            create_item(CatalogItemBody(
                category="SKILL_CATEGORIES", data={"slug": "office", "name": "另一办公"}, sort=0,
            ), self.admin)
        with self.assertRaisesRegex(HTTPException, "name already exists"):
            create_item(CatalogItemBody(
                category="SKILL_CATEGORIES", data={"slug": "office-two", "name": "办公效率"}, sort=0,
            ), self.admin)


if __name__ == "__main__":
    unittest.main()
