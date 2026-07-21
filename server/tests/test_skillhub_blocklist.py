"""Manager-governed SkillHub delisting policy regression (WB-191)."""
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
from routers.catalog import CatalogItemBody, UpdateItemBody, create_item, update_item  # noqa: E402


class SkillHubBlocklistTest(unittest.TestCase):
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

    def test_policy_is_persistent_unique_and_revision_visible(self) -> None:
        item_id = create_item(CatalogItemBody(
            category="SKILLHUB_BLOCKLIST", data={"slug": "tencent-docs", "reason": "not supported"},
        ), self.admin)["id"]
        row = db.get_catalog_item(item_id)
        self.assertEqual("tencent-docs", row["data"]["slug"])
        with self.assertRaisesRegex(HTTPException, "already blocked"):
            create_item(CatalogItemBody(
                category="SKILLHUB_BLOCKLIST", data={"slug": "TENCENT-DOCS"},
            ), self.admin)
        update_item(item_id, UpdateItemBody(data={"slug": "tencent-docs", "reason": "policy"}), self.admin)
        self.assertEqual("policy", db.get_catalog_item(item_id)["data"]["reason"])

    def test_invalid_slug_is_rejected(self) -> None:
        with self.assertRaisesRegex(HTTPException, "invalid SkillHub blocklist slug"):
            create_item(CatalogItemBody(
                category="SKILLHUB_BLOCKLIST", data={"slug": "../escape"},
            ), self.admin)


if __name__ == "__main__":
    unittest.main()
