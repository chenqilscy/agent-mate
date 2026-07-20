"""Server 连接器定义/推荐位契约回归（WB-220）。"""
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
    _validate_connector_definition,
    _validate_connector_recommendation,
    list_all_catalog,
)


class ConnectorRecommendationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        db.get_conn().execute(
            "DELETE FROM catalog_items WHERE category IN ('CONN_DEFS','CONNECTOR_RECOMMENDATIONS')"
        )
        db.get_conn().commit()
        self.definition = {
            "slug": "github", "name": "GitHub", "icon": "🐙", "desc": "仓库管理", "status": "tok",
            "launch": {"command": "npx", "args": ["-y", "mcp-github"],
                       "secret_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"},
                       "requires": ["GITHUB_TOKEN"]},
        }
        _validate_connector_definition(self.definition)
        db.create_catalog_item(category="CONN_DEFS", data=self.definition)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_reference_duplicate_schedule_and_secret_names_are_validated(self) -> None:
        recommendation = {"connector_slug": "github", "placement": "connectors.recommended"}
        _validate_connector_recommendation(recommendation)
        db.create_catalog_item(category="CONNECTOR_RECOMMENDATIONS", data=recommendation)
        with self.assertRaisesRegex(HTTPException, "already exists"):
            _validate_connector_recommendation(recommendation)
        with self.assertRaisesRegex(HTTPException, "does not exist"):
            _validate_connector_recommendation({**recommendation, "connector_slug": "missing"})
        with self.assertRaisesRegex(HTTPException, "end time"):
            _validate_connector_recommendation({**recommendation, "starts_at": 20, "ends_at": 10}, ignore_id="x")
        with self.assertRaisesRegex(HTTPException, "variable names only"):
            _validate_connector_definition({**self.definition, "slug": "unsafe", "name": "Unsafe",
                "launch": {"command": "x", "secret_env": {"TOKEN": "actual-secret-value"}}})

    def test_disabled_recommendation_is_downlinked_for_configured_empty_state(self) -> None:
        rid = db.create_catalog_item(category="CONNECTOR_RECOMMENDATIONS", data={
            "connector_slug": "github", "placement": "connectors.recommended",
        })
        db.update_catalog_item(rid, enabled=False)
        payload = list_all_catalog(False, SimpleNamespace(is_platform_admin=False))
        row = next(item for item in payload["items"] if item["id"] == rid)
        self.assertFalse(row["enabled"])


if __name__ == "__main__":
    unittest.main()
