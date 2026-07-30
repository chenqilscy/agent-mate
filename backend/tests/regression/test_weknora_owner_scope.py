"""WB-328: one local WeKnora tenant connection belongs to one owner."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import weknora  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class WeKnoraOwnerScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = settings.WEKNORA_URL
        self.old_key = settings.WEKNORA_API_KEY
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.WEKNORA_URL = "http://weknora.invalid"
        settings.WEKNORA_API_KEY = "shared-environment-key"
        db._local = threading.local()
        db.init_db()
        db.upsert_external_user("alice", "Alice")
        db.upsert_external_user("bob", "Bob")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        settings.WEKNORA_URL = self.old_url
        settings.WEKNORA_API_KEY = self.old_key
        db._local = threading.local()
        self.tmp.cleanup()

    def test_shared_environment_connection_cannot_cross_owner(self) -> None:
        self.assertTrue(weknora.configured("alice"))
        self.assertFalse(weknora.configured("bob"))
        with patch.object(weknora.httpx, "request") as request:
            with self.assertRaisesRegex(weknora.WeKnoraError, "另一个账号"):
                weknora._request("bob", "GET", "/knowledge-bases")
        request.assert_not_called()

    def test_local_binding_moves_only_to_linked_server_account(self) -> None:
        self.assertTrue(weknora.configured(LOCAL_USER_ID))
        scope = weknora._connection_scope(weknora.conf(LOCAL_USER_ID))
        self.assertEqual(LOCAL_USER_ID, db.get_weknora_connection_owner(scope))
        self.assertFalse(weknora.configured("bob"))
        db.set_server_link(LOCAL_USER_ID, "alice", "Alice")
        self.assertTrue(weknora.configured("alice"))
        self.assertEqual("alice", db.get_weknora_connection_owner(scope))

    def test_independent_owner_key_has_independent_scope(self) -> None:
        self.assertTrue(weknora.configured("alice"))
        db.set_weknora_conf("bob", api_key="bob-private-key")
        self.assertTrue(weknora.configured("bob"))


if __name__ == "__main__":
    unittest.main()
