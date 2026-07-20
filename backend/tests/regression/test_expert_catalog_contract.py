"""App 本地专家人格与 Server 推荐位契约（WB-221）。"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from storage import db  # noqa: E402


class ExpertCatalogContractTest(unittest.TestCase):
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

    def test_server_definition_overrides_runtime_without_touching_custom_experts(self) -> None:
        result = db.replace_server_expert_catalog([
            {"slug": "senior-software-engineer", "name": "高级开发工程师", "avatar": "👨‍💻",
             "intro": "Server 简介", "persona": "Server 运行人格", "tags": ["架构"], "category": "技术工程"},
            {"slug": "bad slug", "name": "非法", "persona": "x"},
        ])
        self.assertEqual({"inserted": 1, "skipped": 1}, result)
        self.assertEqual("Server 运行人格", db.builtin_persona("高级开发工程师"))
        card = next(e for e in db.expert_catalog_specs() if e["slug"] == "senior-software-engineer")
        self.assertEqual("Server 简介", card["intro"])

    def test_recommendations_resolve_schedule_and_configured_empty(self) -> None:
        db.replace_server_expert_catalog([
            {"slug": "architect", "name": "架构师", "avatar": "🏗️", "intro": "系统设计",
             "persona": "架构人格", "tags": ["架构"], "category": "技术工程"},
        ])
        now = time.time()
        db.replace_all_downlink([
            {"category": "EXPERT_RECOMMENDATIONS", "sort": 0, "data": {
                "expert_slug": "architect", "placement": "experts.recommended", "_enabled": True,
            }},
            {"category": "EXPERT_RECOMMENDATIONS", "sort": 1, "data": {
                "expert_slug": "missing", "placement": "experts.recommended", "ends_at": now - 1,
                "_enabled": True,
            }},
        ])
        self.assertEqual(["architect"], [e["slug"] for e in db.showcase_all()["EXPERT_RECOMMENDATIONS"]])
        db.replace_all_downlink([{"category": "EXPERT_RECOMMENDATIONS", "sort": 0, "data": {
            "expert_slug": "architect", "placement": "experts.recommended", "_enabled": False,
        }}])
        self.assertEqual([], db.showcase_all()["EXPERT_RECOMMENDATIONS"])


if __name__ == "__main__":
    unittest.main()
