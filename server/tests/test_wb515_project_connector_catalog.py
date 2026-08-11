"""WB-515 project connector loadout uses the Server-first CONN_DEFS owner."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers.projects import UpdateProjectBody, update_project  # noqa: E402


class ProjectConnectorCatalogContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.project = db.create_project(name="Connector project", owner_id=self.owner.id)
        db.get_conn().execute(
            "DELETE FROM catalog_items WHERE category IN ('CONN_DEFS', 'NP_CONNS')"
        )
        db.get_conn().commit()
        db.create_catalog_item(
            category="CONN_DEFS",
            data={
                "slug": "github",
                "name": "GitHub",
                "icon": "connector",
                "desc": "Repository operations",
                "status": "tok",
            },
        )

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_project_accepts_enabled_conn_defs_and_rejects_unknown_names(self) -> None:
        updated = update_project(
            self.project.id,
            UpdateProjectBody(connectors=["GitHub"]),
            self.owner,
        )
        self.assertEqual(["GitHub"], updated["connectors"])
        with self.assertRaisesRegex(HTTPException, "unknown connectors"):
            update_project(
                self.project.id,
                UpdateProjectBody(connectors=["Missing connector"]),
                self.owner,
            )

    def test_console_queries_the_same_connector_category(self) -> None:
        source = (ROOT / "console" / "src" / "pages" / "ProjectDetailPage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('consoleApi.catalog<CatalogData>("CONN_DEFS")', source)
        self.assertNotIn('consoleApi.catalog<CatalogData>("NP_CONNS")', source)


if __name__ == "__main__":
    unittest.main()
