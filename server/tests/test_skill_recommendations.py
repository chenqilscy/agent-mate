"""Server 推荐位契约回归（WB-217）。"""
from __future__ import annotations

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
from routers.catalog import _validate_skill_recommendation, list_all_catalog  # noqa: E402


class SkillRecommendationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        db.get_conn().execute("DELETE FROM catalog_items WHERE category IN ('APP_SKILLS','SKILL_RECOMMENDATIONS')")
        db.get_conn().commit()
        db.create_catalog_item(
            category="APP_SKILLS", sort=0,
            data={"slug": "web-access", "name": "Web Access", "description": "浏览网页"},
        )

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_agentmate_reference_and_duplicate_are_validated(self) -> None:
        data = {"provider": "agentmate", "skill_slug": "web-access", "placement": "skills.recommended"}
        _validate_skill_recommendation(data)
        db.create_catalog_item(category="SKILL_RECOMMENDATIONS", data=data)
        with self.assertRaisesRegex(HTTPException, "already exists"):
            _validate_skill_recommendation(data)
        with self.assertRaisesRegex(HTTPException, "does not exist"):
            _validate_skill_recommendation({**data, "skill_slug": "missing"})

    def test_skillhub_metadata_and_schedule_are_validated(self) -> None:
        _validate_skill_recommendation({
            "provider": "skillhub", "skill_slug": "community-skill",
            "placement": "skills.recommended", "title": "社区技能", "description": "商店描述",
            "starts_at": 100, "ends_at": 200,
        })
        with self.assertRaisesRegex(HTTPException, "title and description"):
            _validate_skill_recommendation({
                "provider": "skillhub", "skill_slug": "community-skill",
                "placement": "skills.recommended",
            })
        with self.assertRaisesRegex(HTTPException, "end time"):
            _validate_skill_recommendation({
                "provider": "skillhub", "skill_slug": "community-skill",
                "placement": "skills.recommended", "title": "社区技能", "description": "商店描述",
                "starts_at": 200, "ends_at": 100,
            })

    def test_disabled_recommendation_is_downlinked_to_preserve_configured_empty_state(self) -> None:
        rid = db.create_catalog_item(category="SKILL_RECOMMENDATIONS", data={
            "provider": "agentmate", "skill_slug": "web-access", "placement": "skills.recommended",
        })
        db.update_catalog_item(rid, enabled=False)
        payload = list_all_catalog(False, SimpleNamespace(is_platform_admin=False))
        row = next(item for item in payload["items"] if item["id"] == rid)
        self.assertFalse(row["enabled"])

    def test_existing_skill_definitions_are_migrated_once(self) -> None:
        db.get_conn().execute("DELETE FROM settings WHERE k='skill_recommendations_v2'")
        db.get_conn().commit()
        db.init_db()
        rows = db.list_catalog_items("SKILL_RECOMMENDATIONS", scope="builtin", include_disabled=True)
        self.assertEqual(["web-access"], [row["data"]["skill_slug"] for row in rows])
        db.delete_catalog_item(rows[0]["id"])
        db.init_db()
        self.assertEqual([], db.list_catalog_items("SKILL_RECOMMENDATIONS", scope="builtin", include_disabled=True))


if __name__ == "__main__":
    unittest.main()
