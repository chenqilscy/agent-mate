"""WB-326 local token expiry, logout and durable remote revocation."""
from __future__ import annotations

import asyncio
import sys
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import server_sync  # noqa: E402
from auth import deps  # noqa: E402
import auth.middleware as auth_middleware  # noqa: E402
from config import settings  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from storage import db  # noqa: E402


class LocalTokenLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = settings.AGENTMATE_SERVER_URL
        self.old_validation_ttl = settings.SERVER_TOKEN_VALIDATION_TTL_SECONDS
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        settings.SERVER_TOKEN_VALIDATION_TTL_SECONDS = 30
        db.init_db()
        db.upsert_external_user("account-1", "Alice")

    def tearDown(self) -> None:
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url
        settings.SERVER_TOKEN_VALIDATION_TTL_SECONDS = self.old_validation_ttl
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _cache(self, token: str = "server-token", expires_at: float | None = None) -> None:
        db.cache_token(token, "account-1", expires_at or time.time() + 120)
        db.set_server_identity("account-1", token)

    def test_cached_token_expires_offline_and_clears_identity(self) -> None:
        self._cache(expires_at=time.time() + 120)
        self.assertEqual("account-1", deps.resolve_token_to_user_id("server-token"))
        db.get_conn().execute(
            "UPDATE auth_tokens SET expires_at=? WHERE token=?",
            (time.time() - 1, "server-token"),
        )
        db.get_conn().commit()
        self.assertIsNone(deps.resolve_token_to_user_id("server-token"))
        self.assertIsNone(db.get_server_identity("account-1"))

    def test_online_revocation_is_observed_after_the_declared_validation_window(self) -> None:
        self._cache()
        db.get_conn().execute(
            "UPDATE auth_tokens SET validated_at=? WHERE token=?",
            (time.time() - settings.SERVER_TOKEN_VALIDATION_TTL_SECONDS - 1, "server-token"),
        )
        db.get_conn().commit()
        self.assertIsNone(deps.resolve_token_to_user_id("server-token"))
        with patch.object(
            deps.server_client, "verify_token_state", return_value=("invalid", None),
        ):
            self.assertIsNone(deps.resolve_via_server("server-token"))
        self.assertIsNone(db.user_id_for_token("server-token"))

    def test_offline_logout_is_local_first_and_retries_remote_revocation(self) -> None:
        self._cache()
        with patch.object(auth_router.server_client, "server_logout", return_value=False):
            result = auth_router.logout("Bearer server-token")
        self.assertTrue(result["pending"])
        self.assertIsNone(db.user_id_for_token("server-token"))
        self.assertIsNone(db.get_server_identity("account-1"))
        self.assertTrue(db.is_token_revocation_pending("server-token"))
        self.assertIsNone(deps.resolve_via_server("server-token"))

        with patch.object(server_sync.server_client, "server_logout", return_value=True):
            flushed = server_sync.flush_outbox()
        self.assertEqual({"pushed": 0, "pending": 0}, flushed)
        self.assertFalse(db.is_token_revocation_pending("server-token"))

    def test_online_logout_removes_pending_record_immediately(self) -> None:
        self._cache()
        with patch.object(auth_router.server_client, "server_logout", return_value=True):
            result = auth_router.logout("Bearer server-token")
        self.assertTrue(result["revoked_remote"])
        self.assertFalse(result["pending"])
        self.assertFalse(db.is_token_revocation_pending("server-token"))

    def test_legacy_cached_token_gets_bounded_expiry_idempotently(self) -> None:
        self._close_connection()
        legacy_path = Path(self.tmp.name) / "legacy-app.db"
        raw = sqlite3.connect(legacy_path)
        raw.execute(
            "CREATE TABLE auth_tokens "
            "(token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        raw.execute(
            "INSERT INTO auth_tokens (token,user_id,created_at) VALUES (?,?,?)",
            ("legacy-token", "account-1", time.time() - 86400),
        )
        raw.commit()
        raw.close()

        settings.DB_PATH = legacy_path
        before = time.time()
        db.init_db()
        row = db.get_conn().execute(
            "SELECT expires_at FROM auth_tokens WHERE token='legacy-token'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(
            row["expires_at"], before + settings.SERVER_TOKEN_LEGACY_GRACE_SECONDS - 1
        )
        db.init_db()

    def test_supplied_invalid_bearer_never_downgrades_to_guest(self) -> None:
        async def status(path: str, authorization: bytes | None) -> int:
            messages: list[dict] = []

            async def app(scope, receive, send) -> None:
                await send({"type": "http.response.start", "status": 204, "headers": []})
                await send({"type": "http.response.body", "body": b""})

            headers = [] if authorization is None else [(b"authorization", authorization)]
            scope = {
                "type": "http", "method": "GET", "path": path,
                "headers": headers,
            }
            async def receive() -> dict:
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message: dict) -> None:
                messages.append(message)

            await auth_middleware.AuthMiddleware(app)(scope, receive, send)
            return messages[0]["status"]

        with (
            patch.object(auth_middleware, "resolve_token_to_user_id", return_value=None),
            patch.object(auth_middleware.server_client, "server_enabled", return_value=False),
        ):
            self.assertEqual(
                401,
                asyncio.run(status("/api/projects", b"Bearer forged-token")),
            )
            self.assertEqual(
                401,
                asyncio.run(status("/api/projects", b"Basic credentials")),
            )
            self.assertEqual(204, asyncio.run(status("/api/projects", None)))
            self.assertEqual(
                204,
                asyncio.run(status("/api/health", b"Bearer forged-token")),
            )


if __name__ == "__main__":
    unittest.main()
