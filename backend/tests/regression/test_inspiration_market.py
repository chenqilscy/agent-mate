"""WB-321: inspiration templates and favorites form an owner-scoped real workflow."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers import catalog as router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class InspirationMarketTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        db._local = threading.local()
        db.init_db()
        set_current_user_id(None)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        set_current_user_id(None)
        self.tmp.cleanup()

    def test_templates_are_typed_and_executable(self) -> None:
        templates = router.get_catalog()["INSP_TEMPLATES"]
        self.assertGreaterEqual(len(templates), 8)
        for item in templates:
            self.assertTrue(item["id"])
            self.assertTrue(item["category"])
            self.assertTrue(item["artifactType"])
            self.assertTrue(item["prompt"])
            self.assertTrue(item["preview"]["items"])

    def test_favorites_are_idempotent_persistent_and_owner_scoped(self) -> None:
        template_id = router.get_catalog()["INSP_TEMPLATES"][0]["id"]
        body = router.InspirationFavoriteBody(favorite=True)
        self.assertEqual([template_id], router.put_inspiration_favorite(template_id, body)["ids"])
        self.assertEqual([template_id], router.put_inspiration_favorite(template_id, body)["ids"])

        other = db.create_user(name="other", password="test-password")
        set_current_user_id(other.id)
        self.assertEqual([], router.get_inspiration_favorites()["ids"])
        router.put_inspiration_favorite(template_id, body)

        set_current_user_id(LOCAL_USER_ID)
        self.assertEqual([template_id], router.get_inspiration_favorites()["ids"])

        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        db.init_db()
        self.assertEqual([template_id], router.get_inspiration_favorites()["ids"])

        self.assertEqual([], router.put_inspiration_favorite(
            template_id, router.InspirationFavoriteBody(favorite=False),
        )["ids"])

    def test_unknown_template_cannot_be_favorited(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            router.put_inspiration_favorite(
                "missing-template", router.InspirationFavoriteBody(favorite=True),
            )
        self.assertEqual(404, ctx.exception.status_code)


if __name__ == "__main__":
    unittest.main()
