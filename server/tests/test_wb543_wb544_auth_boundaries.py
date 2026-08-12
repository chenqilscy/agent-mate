"""WB-543..545 registration atomicity and independent login throttles."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import sso_store  # noqa: E402
from config import settings  # noqa: E402
from routers import auth  # noqa: E402


class AuthConcurrencyAndRateLimitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_policy = settings.SSO_REGISTRATION_POLICY
        self.old_rate = settings.AUTH_RATE_LIMIT_PER_MINUTE
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        settings.SSO_REGISTRATION_POLICY = "open"
        settings.AUTH_RATE_LIMIT_PER_MINUTE = 100
        db._local = threading.local()
        db.init_db()
        app = FastAPI()
        app.include_router(auth.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self._close_thread_connection()
        db._local = threading.local()
        settings.DB_PATH = self.old_db
        settings.SSO_REGISTRATION_POLICY = self.old_policy
        settings.AUTH_RATE_LIMIT_PER_MINUTE = self.old_rate
        self.temp.cleanup()

    @staticmethod
    def _close_thread_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _register_race(self, names: tuple[str, ...]) -> tuple[list[tuple], list[Exception]]:
        barrier = threading.Barrier(len(names))
        lock = threading.Lock()
        successes: list[tuple] = []
        failures: list[Exception] = []

        def register(name: str) -> None:
            try:
                barrier.wait(timeout=5)
                result = db.register_password_account(
                    name=name, password="ConcurrentPassword-123",
                    email=f"{name}@example.com",
                )
                with lock:
                    successes.append(result)
            except Exception as exc:  # capture the race result for assertions
                with lock:
                    failures.append(exc)
            finally:
                self._close_thread_connection()

        threads = [threading.Thread(target=register, args=(name,)) for name in names]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "registration race deadlocked")
        return successes, failures

    @staticmethod
    def _request(ip: str) -> Request:
        return Request({
            "type": "http", "http_version": "1.1", "method": "POST",
            "scheme": "http", "path": "/api/auth/login", "raw_path": b"/api/auth/login",
            "query_string": b"", "headers": [], "client": (ip, 12345),
            "server": ("testserver", 80),
        })

    def _login_status(self, name: str, ip: str) -> int:
        try:
            auth.login(
                auth.LoginBody(name=name, password="wrong-password"),
                self._request(ip), Response(),
            )
        except HTTPException as exc:
            return exc.status_code
        return 200

    def test_concurrent_first_registration_elects_exactly_one_admin(self) -> None:
        successes, failures = self._register_race(("first-a", "first-b", "first-c"))
        self.assertEqual([], failures)
        self.assertEqual(3, len(successes))
        self.assertEqual(1, sum(account.is_platform_admin for account, _token, _expiry in successes))
        self.assertEqual(1, db.count_platform_admins())
        self.assertEqual(
            ["bootstrap_first_admin", "password_registered", "password_registered"],
            sorted(row["action"] for row in db.list_auth_audit()),
        )
        for account, token, expires_at in successes:
            self.assertEqual(account.id, db.account_id_for_token(token))
            self.assertGreater(expires_at, 0)

    def test_concurrent_duplicate_registration_is_conflict_not_server_error(self) -> None:
        successes, failures = self._register_race(("same-name", "same-name"))
        self.assertEqual(1, len(successes))
        self.assertEqual(["name already taken"], [str(exc) for exc in failures])
        duplicate = self.client.post("/api/auth/register", json={
            "name": "same-name", "password": "ConcurrentPassword-123",
            "email": "duplicate@example.com",
        })
        self.assertEqual(409, duplicate.status_code, duplicate.text)

    def test_login_throttles_source_and_account_as_independent_buckets(self) -> None:
        settings.AUTH_RATE_LIMIT_PER_MINUTE = 2
        self.assertEqual(
            [401, 401, 429],
            [self._login_status(f"sweep-{number}", "198.51.100.1") for number in range(3)],
        )
        db.get_conn().execute("DELETE FROM auth_rate_windows")
        db.get_conn().commit()
        self.assertEqual(
            [401, 401, 429],
            [self._login_status("target-account", f"198.51.100.{number}") for number in range(1, 4)],
        )

    def test_sso_first_registration_becomes_the_only_platform_admin(self) -> None:
        first_id = sso_store.resolve_identity(
            {"provider": "google", "mode": "login"},
            {"subject": "first-sso", "email": "first-sso@example.com", "name": "First SSO"},
        )
        second_id = sso_store.resolve_identity(
            {"provider": "google", "mode": "login"},
            {"subject": "second-sso", "email": "second-sso@example.com", "name": "Second SSO"},
        )
        self.assertTrue(db.get_account(first_id).is_platform_admin)
        self.assertFalse(db.get_account(second_id).is_platform_admin)
        self.assertEqual(1, db.count_platform_admins())
        first_audit = db.list_auth_audit(account_id=first_id)
        self.assertEqual("bootstrap_first_admin", first_audit[-1]["action"])
        self.assertEqual("google", first_audit[-1]["provider"])

    def test_password_and_sso_registration_share_one_first_admin_election(self) -> None:
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        failures: list[Exception] = []

        def password_register() -> None:
            try:
                barrier.wait(timeout=5)
                db.register_password_account(name="password-first", password="Password-123")
            except Exception as exc:
                with lock:
                    failures.append(exc)
            finally:
                self._close_thread_connection()

        def sso_register() -> None:
            try:
                barrier.wait(timeout=5)
                sso_store.resolve_identity(
                    {"provider": "google", "mode": "login"},
                    {"subject": "mixed-sso", "email": "mixed@example.com", "name": "Mixed SSO"},
                )
            except Exception as exc:
                with lock:
                    failures.append(exc)
            finally:
                self._close_thread_connection()

        threads = [threading.Thread(target=password_register), threading.Thread(target=sso_register)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "mixed registration race deadlocked")
        self.assertEqual([], failures)
        self.assertEqual(2, db.count_accounts())
        self.assertEqual(1, db.count_platform_admins())

    def test_concurrent_sso_email_registration_requires_explicit_link(self) -> None:
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        successes: list[str] = []
        failures: list[Exception] = []

        def register(subject: str) -> None:
            try:
                barrier.wait(timeout=5)
                account_id = sso_store.resolve_identity(
                    {"provider": "google", "mode": "login"},
                    {"subject": subject, "email": "shared@example.com", "name": subject},
                )
                with lock:
                    successes.append(account_id)
            except Exception as exc:
                with lock:
                    failures.append(exc)
            finally:
                self._close_thread_connection()

        threads = [threading.Thread(target=register, args=(subject,)) for subject in ("sso-a", "sso-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "SSO registration race deadlocked")
        self.assertEqual(1, len(successes))
        self.assertEqual(["explicit_link_required"], [str(exc) for exc in failures])
        self.assertEqual(1, db.count_accounts())


if __name__ == "__main__":
    unittest.main()
