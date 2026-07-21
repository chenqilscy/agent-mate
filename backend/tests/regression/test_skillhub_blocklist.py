"""Local SkillHub browse/install enforcement for Manager policy (WB-191)."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import skills_store  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers import skills as skills_router  # noqa: E402
from storage import db  # noqa: E402


class SkillHubBlocklistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "agentmate.db"
        db._local = threading.local()
        db.init_db()
        db.replace_all_downlink([{
            "category": "SKILLHUB_BLOCKLIST", "sort": 0,
            "data": {"slug": "tencent-docs", "reason": "unsupported integration"},
        }])

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        db._local = threading.local()
        self.tmp.cleanup()

    def test_browse_filters_blocked_slug_and_keeps_other_cards(self) -> None:
        cards = [
            {"slug": "tencent-docs", "name": "Tencent Docs", "category": "office"},
            {"slug": "csv-tools", "name": "CSV", "category": "office"},
        ]
        with patch.object(skills_store, "scan", return_value=[]):
            result = skills_store.decorate_cards(cards)
        self.assertEqual(["csv-tools"], [item["slug"] for item in result])
        self.assertEqual("unsupported integration", skills_store.market_block_reason("TENCENT-DOCS"))

    def test_direct_install_is_rejected_before_cli_execution(self) -> None:
        with (
            patch.object(skills_router, "_scope_owner", return_value="owner"),
            patch.object(skills_store, "cli_available", return_value=True),
            patch.object(skills_store, "install") as install,
        ):
            with self.assertRaisesRegex(HTTPException, "已由平台下架") as raised:
                skills_router.install_skill(skills_router.InstallBody(slug="tencent-docs"))
        self.assertEqual(409, raised.exception.status_code)
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
