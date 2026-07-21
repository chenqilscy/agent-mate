"""App 目录按 Server 管理分类排序并兼容旧下行（WB-267）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from storage import db  # noqa: E402


class SkillCategoryOrderingTest(unittest.TestCase):
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

    def test_managed_category_order_controls_visible_app_filters(self) -> None:
        db.replace_all_downlink([
            {"category": "SKILL_CATEGORIES", "sort": 10, "data": {"slug": "data", "name": "数据分析"}},
            {"category": "SKILL_CATEGORIES", "sort": 20, "data": {"slug": "development", "name": "开发编程"}},
            {"category": "SKILL_RECOMMENDATIONS", "sort": 10, "data": {
                "provider": "agentmate", "skill_slug": "web-access", "category": "开发编程",
                "placement": "skills.recommended", "_enabled": True,
            }},
            {"category": "SKILL_RECOMMENDATIONS", "sort": 20, "data": {
                "provider": "agentmate", "skill_slug": "excel-csv", "category": "数据分析",
                "placement": "skills.recommended", "_enabled": True,
            }},
        ])
        self.assertEqual(["全部", "数据分析", "开发编程"], db.showcase_all()["SK_CATS"])

    def test_legacy_server_without_managed_categories_keeps_safe_fallback(self) -> None:
        db.replace_all_downlink([{"category": "SKILL_RECOMMENDATIONS", "sort": 0, "data": {
            "provider": "agentmate", "skill_slug": "web-access", "category": "开发编程",
            "placement": "skills.recommended", "_enabled": True,
        }}])
        self.assertEqual(["全部", "开发编程"], db.showcase_all()["SK_CATS"])


if __name__ == "__main__":
    unittest.main()
