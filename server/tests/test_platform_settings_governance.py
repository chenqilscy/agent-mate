"""WB-291: platform setting registry, secret boundary, audit and hot reload."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import platform_settings  # noqa: E402
import weknora  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers import platform_settings as router  # noqa: E402


class PlatformSettingsGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_values = {
            "WEKNORA_URL": settings.WEKNORA_URL,
            "WEKNORA_API_KEY": settings.WEKNORA_API_KEY,
            "WEKNORA_EMBEDDING_MODEL_ID": settings.WEKNORA_EMBEDDING_MODEL_ID,
            "INVITE_TTL": settings.INVITE_TTL,
        }
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        settings.WEKNORA_URL = "http://env-weknora"
        settings.WEKNORA_API_KEY = "env-secret"
        settings.WEKNORA_EMBEDDING_MODEL_ID = "env-embedding"
        settings.INVITE_TTL = 604800
        db._local = threading.local(); db.init_db()
        self.admin = db.create_account(name="admin", password="password123")
        self.admin.is_platform_admin = True
        self.user = db.create_account(name="user", password="password123")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        for key, value in self.old_values.items():
            setattr(settings, key, value)
        db._local = threading.local(); self.tmp.cleanup()

    def test_admin_only_secret_write_is_masked_and_audited(self) -> None:
        with self.assertRaisesRegex(HTTPException, "admin"):
            router.get_platform_settings(self.user)
        result = router.put_platform_settings(router.UpdateBody(values={
            "knowledge.weknora_url": "http://db-weknora:8080/",
            "knowledge.weknora_api_key": "database-secret",
            "collaboration.invite_ttl_seconds": 3600,
        }), self.admin)
        rendered = repr(result)
        self.assertNotIn("database-secret", rendered)
        self.assertNotIn("env-secret", rendered)
        self.assertEqual("http://db-weknora:8080", platform_settings.effective("knowledge.weknora_url"))
        self.assertEqual("database-secret", platform_settings.effective("knowledge.weknora_api_key"))
        self.assertEqual(3600, platform_settings.effective("collaboration.invite_ttl_seconds"))
        self.assertNotIn("database-secret", repr(db.list_platform_settings_audit()))

    def test_clear_restores_fallback_and_deployment_keys_are_rejected_atomically(self) -> None:
        router.put_platform_settings(router.UpdateBody(values={
            "knowledge.weknora_url": "http://db-weknora",
        }), self.admin)
        restored = router.put_platform_settings(router.UpdateBody(clear=[
            "knowledge.weknora_url",
        ]), self.admin)
        item = next(row for row in restored["items"] if row["key"] == "knowledge.weknora_url")
        self.assertEqual("http://env-weknora", item["value"])
        with self.assertRaisesRegex(HTTPException, "启动级配置"):
            router.put_platform_settings(router.UpdateBody(values={
                "knowledge.weknora_url": "http://must-not-write",
                "server.database_path": "elsewhere.db",
            }), self.admin)
        self.assertEqual("http://env-weknora", platform_settings.effective("knowledge.weknora_url"))
        with self.assertRaisesRegex(HTTPException, "必须是整数"):
            router.put_platform_settings(router.UpdateBody(values={
                "collaboration.invite_ttl_seconds": 1.5,
            }), self.admin)

    @patch.object(weknora.httpx, "request")
    def test_weknora_client_reads_database_setting_without_restart(self, request) -> None:
        class Response:
            status_code = 200
            content = b'{"success":true,"data":[]}'
            text = content.decode()
            def json(self): return {"success": True, "data": []}
        request.return_value = Response()
        router.put_platform_settings(router.UpdateBody(values={
            "knowledge.weknora_url": "http://hot-weknora:9090",
            "knowledge.weknora_api_key": "hot-secret",
        }), self.admin)
        weknora.list_models()
        _, url = request.call_args.args[:2]
        self.assertEqual("http://hot-weknora:9090/api/v1/models", url)
        self.assertEqual("hot-secret", request.call_args.kwargs["headers"]["X-API-Key"])


if __name__ == "__main__":
    unittest.main()
