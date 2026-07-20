"""Server 专家定义/推荐位契约回归（WB-221）。"""
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
from routers.catalog import (  # noqa: E402
    _validate_expert_definition,
    _validate_expert_recommendation,
    list_all_catalog,
)


class ExpertRecommendationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        db.get_conn().execute(
            "DELETE FROM catalog_items WHERE category IN ('EXPERT_DEFS','EXPERT_RECOMMENDATIONS')"
        )
        db.get_conn().commit()
        self.definition = {
            "slug": "architect", "name": "架构师", "avatar": "🏗️", "persona": "以架构师身份作答。",
            "intro": "系统设计", "tags": ["架构"], "category": "技术工程", "functional": True,
        }
        _validate_expert_definition(self.definition)
        db.create_catalog_item(category="EXPERT_DEFS", data=self.definition)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_definition_reference_duplicate_and_schedule_are_validated(self) -> None:
        recommendation = {"expert_slug": "architect", "placement": "experts.recommended"}
        _validate_expert_recommendation(recommendation)
        db.create_catalog_item(category="EXPERT_RECOMMENDATIONS", data=recommendation)
        with self.assertRaisesRegex(HTTPException, "already exists"):
            _validate_expert_recommendation(recommendation)
        with self.assertRaisesRegex(HTTPException, "does not exist"):
            _validate_expert_recommendation({**recommendation, "expert_slug": "missing"})
        with self.assertRaisesRegex(HTTPException, "end time"):
            _validate_expert_recommendation({**recommendation, "starts_at": 20, "ends_at": 10}, ignore_id="x")
        with self.assertRaisesRegex(HTTPException, "name and persona"):
            _validate_expert_definition({**self.definition, "slug": "empty-persona", "name": "空", "persona": ""})

    def test_disabled_recommendation_is_downlinked_for_configured_empty_state(self) -> None:
        rid = db.create_catalog_item(category="EXPERT_RECOMMENDATIONS", data={
            "expert_slug": "architect", "placement": "experts.recommended",
        })
        db.update_catalog_item(rid, enabled=False)
        payload = list_all_catalog(False, SimpleNamespace(is_platform_admin=False))
        row = next(item for item in payload["items"] if item["id"] == rid)
        self.assertFalse(row["enabled"])


if __name__ == "__main__":
    unittest.main()
