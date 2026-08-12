"""WB-539: Console uses a same-origin HttpOnly cookie while Bearer clients remain valid."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from console_session import ConsoleCsrfMiddleware  # noqa: E402
from config import settings  # noqa: E402
from routers import auth  # noqa: E402
from security_headers import SecurityHeadersMiddleware  # noqa: E402


class ConsoleHttpOnlySessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self.old_rate = settings.AUTH_RATE_LIMIT_PER_MINUTE
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        settings.AUTH_RATE_LIMIT_PER_MINUTE = 100
        db._local = threading.local()
        db.init_db()
        db.create_account(name="console-user", password="ConsolePassword-123")
        app = FastAPI()
        app.add_middleware(ConsoleCsrfMiddleware)
        app.add_middleware(SecurityHeadersMiddleware)
        app.include_router(auth.router)
        self.app = app

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        settings.DB_PATH = self.old_path
        settings.AUTH_RATE_LIMIT_PER_MINUTE = self.old_rate
        self.temp.cleanup()

    def test_console_cookie_restores_session_rejects_csrf_and_logs_out(self) -> None:
        origin = "https://server.example.test"
        headers = {"X-AgentMate-Console-Session": "1", "Origin": origin}
        with TestClient(self.app, base_url=origin) as client:
            login = client.post(
                "/api/auth/login",
                headers=headers,
                json={"name": "console-user", "password": "ConsolePassword-123"},
            )
            self.assertEqual(200, login.status_code, login.text)
            self.assertNotIn("token", login.json())
            cookie = login.headers.get("set-cookie", "")
            self.assertIn("agentmate_console_session=", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("Secure", cookie)
            self.assertIn("SameSite=strict", cookie)
            self.assertEqual(200, client.get("/api/me").status_code)

            rejected = client.post(
                "/api/auth/logout",
                headers={"X-AgentMate-Console-Session": "1", "Origin": "https://evil.test"},
            )
            self.assertEqual(403, rejected.status_code)
            self.assertEqual("DENY", rejected.headers.get("x-frame-options"))
            self.assertEqual(200, client.get("/api/me").status_code)

            logout = client.post("/api/auth/logout", headers=headers)
            self.assertEqual(200, logout.status_code)
            self.assertIn("Max-Age=0", logout.headers.get("set-cookie", ""))
            self.assertEqual(401, client.get("/api/me").status_code)

    def test_bearer_login_contract_remains_available_for_desktop_clients(self) -> None:
        with TestClient(self.app, base_url="https://server.example.test") as client:
            login = client.post(
                "/api/auth/login",
                json={"name": "console-user", "password": "ConsolePassword-123"},
            )
            self.assertEqual(200, login.status_code, login.text)
            token = login.json().get("token")
            self.assertTrue(token)
            self.assertNotIn("set-cookie", login.headers)
            me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(200, me.status_code, me.text)


if __name__ == "__main__":
    unittest.main()
