"""Account registration, revocation and login-method lifecycle (WB-366..368)."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import relay_store  # noqa: E402
import sso_store  # noqa: E402
from config import settings  # noqa: E402
from routers import accounts, auth  # noqa: E402


class AccountSecurityLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self.old_policy = settings.SSO_REGISTRATION_POLICY
        self.old_bootstrap = settings.BOOTSTRAP_ADMIN_SECRET
        self.old_rate = settings.AUTH_RATE_LIMIT_PER_MINUTE
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        settings.SSO_REGISTRATION_POLICY = "invite_only"
        settings.BOOTSTRAP_ADMIN_SECRET = "one-time-bootstrap-secret"
        settings.AUTH_RATE_LIMIT_PER_MINUTE = 100
        db._local = threading.local()
        db.init_db()
        app = FastAPI()
        app.include_router(auth.router)
        app.include_router(accounts.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        settings.DB_PATH = self.old_path
        settings.SSO_REGISTRATION_POLICY = self.old_policy
        settings.BOOTSTRAP_ADMIN_SECRET = self.old_bootstrap
        settings.AUTH_RATE_LIMIT_PER_MINUTE = self.old_rate
        self.temp.cleanup()

    def _bootstrap(self) -> tuple[dict, dict[str, str]]:
        response = self.client.post("/api/auth/bootstrap", json={
            "name": "admin", "password": "AdminPassword-123",
            "email": "admin@example.com",
            "bootstrap_secret": "one-time-bootstrap-secret",
        })
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        return payload["account"], {"Authorization": f"Bearer {payload['token']}"}

    def _race(self, *operations) -> list[str]:
        barrier = threading.Barrier(len(operations))
        results: list[str] = []

        def run(operation) -> None:
            barrier.wait()
            try:
                operation()
                results.append("ok")
            except ValueError as exc:
                results.append(str(exc))
            finally:
                conn = getattr(db._local, "conn", None)
                if conn is not None:
                    conn.close()

        threads = [threading.Thread(target=run, args=(operation,)) for operation in operations]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "concurrent invariant test deadlocked")
        return results

    def _add_identity(self, account_id: str, provider: str) -> None:
        db.get_conn().execute(
            "INSERT INTO external_identities "
            "(id,account_id,provider,subject,email,display_name,created_at,last_login_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (db.new_uuid(), account_id, provider, f"{provider}-subject", "", provider,
             time.time(), time.time()),
        )
        db.get_conn().commit()

    def test_registration_policy_and_bootstrap_are_fail_closed(self) -> None:
        blocked = self.client.post("/api/auth/register", json={
            "name": "attacker", "password": "AttackerPass-123",
        })
        self.assertEqual(403, blocked.status_code)

        admin, _headers = self._bootstrap()
        self.assertTrue(admin["is_platform_admin"])
        again = self.client.post("/api/auth/bootstrap", json={
            "name": "second", "password": "SecondPassword-123",
            "bootstrap_secret": "one-time-bootstrap-secret",
        })
        self.assertEqual(409, again.status_code)

        settings.SSO_REGISTRATION_POLICY = "open"
        registered = self.client.post("/api/auth/register", json={
            "name": "member", "password": "MemberPassword-123",
        })
        self.assertEqual(200, registered.status_code, registered.text)
        self.assertFalse(registered.json()["account"]["is_platform_admin"])

    def test_delete_revokes_every_credential_and_identity_atomically(self) -> None:
        _admin, headers = self._bootstrap()
        user = db.create_account(name="member", password="MemberPassword-123")
        human_token = db.create_token(user.id)[0]
        _service, service_token = relay_store.create_service_account(
            user.id, "ci", ["relay:read", "relay:write"],
        )
        db.get_conn().execute(
            "INSERT INTO external_identities "
            "(id,account_id,provider,subject,email,display_name,created_at,last_login_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (db.new_uuid(), user.id, "google", "subject-1", "member@example.com",
             "Member", time.time(), time.time()),
        )
        db.get_conn().commit()

        deleted = self.client.delete(f"/api/accounts/{user.id}", headers=headers)
        self.assertEqual(200, deleted.status_code, deleted.text)
        self.assertIsNone(db.account_id_for_token(human_token))
        self.assertIsNone(relay_store.resolve_service_token(service_token))
        self.assertEqual(0, db.get_conn().execute(
            "SELECT COUNT(*) FROM external_identities WHERE account_id=?", (user.id,),
        ).fetchone()[0])
        self.assertEqual(0, db.get_conn().execute(
            "SELECT COUNT(*) FROM service_accounts WHERE owner_id=?", (user.id,),
        ).fetchone()[0])

    def test_password_reset_suspension_sessions_and_audit(self) -> None:
        _admin, headers = self._bootstrap()
        user = db.create_account(
            name="sso-user", password="unused-generated-secret",
            password_login_enabled=False,
        )
        db.get_conn().execute(
            "INSERT INTO external_identities "
            "(id,account_id,provider,subject,email,display_name,created_at,last_login_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (db.new_uuid(), user.id, "google", "subject-2", "", "SSO", time.time(), time.time()),
        )
        db.get_conn().commit()

        reset = self.client.post(
            f"/api/accounts/{user.id}/password", headers=headers,
            json={"password": "RecoveredPass-123"},
        )
        self.assertEqual(200, reset.status_code, reset.text)
        login = self.client.post("/api/auth/login", json={
            "name": "sso-user", "password": "RecoveredPass-123",
        })
        self.assertEqual(200, login.status_code, login.text)
        user_token = login.json()["token"]
        _service, service_token = relay_store.create_service_account(
            user.id, "automation", ["relay:read"],
        )

        suspended = self.client.put(
            f"/api/accounts/{user.id}/suspension", headers=headers,
            json={"suspended": True},
        )
        self.assertEqual(200, suspended.status_code, suspended.text)
        self.assertIsNone(db.account_id_for_token(user_token))
        self.assertIsNone(relay_store.resolve_service_token(service_token))
        self.assertEqual(401, self.client.post("/api/auth/login", json={
            "name": "sso-user", "password": "RecoveredPass-123",
        }).status_code)
        actions = {item["action"] for item in db.list_auth_audit(account_id=user.id)}
        self.assertIn("password_reset", actions)
        self.assertIn("account_suspended", actions)

    def test_admin_identity_unlink_revokes_sessions_in_the_same_store_transaction(self) -> None:
        _admin, headers = self._bootstrap()
        user = db.create_account(name="linked-user", password="LinkedPassword-123")
        self._add_identity(user.id, "google")
        user_token = db.create_token(user.id)[0]
        response = self.client.delete(
            f"/api/accounts/{user.id}/identities/google", headers=headers,
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertIsNone(db.account_id_for_token(user_token))
        actions = [item["action"] for item in db.list_auth_audit(account_id=user.id)]
        self.assertEqual(1, actions.count("identity_unlinked"))

    def test_platform_admin_role_change_is_audited_atomically(self) -> None:
        admin, headers = self._bootstrap()
        user = db.create_account(name="operator", password="OperatorPass-123")
        granted = self.client.patch(
            f"/api/accounts/{user.id}", headers=headers,
            json={"is_platform_admin": True},
        )
        self.assertEqual(200, granted.status_code, granted.text)
        audit = db.list_auth_audit(account_id=user.id)
        item = next(entry for entry in audit if entry["action"] == "platform_admin_granted")
        self.assertEqual(admin["id"], item["actor_id"])
        self.assertEqual({"before": False, "after": True}, item["details"])

    def test_concurrent_admin_demotion_preserves_one_active_admin(self) -> None:
        admin, _headers = self._bootstrap()
        second = db.create_account(
            name="second-admin", password="SecondAdminPass-123", is_platform_admin=True,
        )
        results = self._race(
            lambda: db.update_account(admin["id"], is_platform_admin=False, actor_id="system"),
            lambda: db.update_account(second.id, is_platform_admin=False, actor_id="system"),
        )
        self.assertCountEqual(["ok", "last_platform_admin"], results)
        self.assertEqual(1, db.count_platform_admins())
        revoked = [item for item in db.list_auth_audit() if item["action"] == "platform_admin_revoked"]
        self.assertEqual(1, len(revoked))

    def test_concurrent_admin_suspension_and_delete_preserve_one_admin(self) -> None:
        admin, _headers = self._bootstrap()
        second = db.create_account(
            name="second-admin", password="SecondAdminPass-123", is_platform_admin=True,
        )
        suspension = self._race(
            lambda: db.set_account_suspended(admin["id"], True, actor_id="system"),
            lambda: db.set_account_suspended(second.id, True, actor_id="system"),
        )
        self.assertCountEqual(["ok", "last_platform_admin"], suspension)
        self.assertEqual(1, db.count_platform_admins())

        # Reactivate the suspended account, then race destructive deletion.
        suspended_id = admin["id"] if db.get_account(admin["id"]).suspended_at > 0 else second.id
        db.set_account_suspended(suspended_id, False, actor_id="system")
        deletion = self._race(
            lambda: db.delete_account(admin["id"], actor_id="system"),
            lambda: db.delete_account(second.id, actor_id="system"),
        )
        self.assertCountEqual(["ok", "last_platform_admin"], deletion)
        self.assertEqual(1, db.count_platform_admins())

    def test_concurrent_login_method_changes_cannot_lock_out_account(self) -> None:
        user = db.create_account(name="hybrid", password="HybridPassword-123")
        self._add_identity(user.id, "google")
        results = self._race(
            lambda: db.set_password_login_enabled(user.id, False, actor_id="system"),
            lambda: sso_store.unlink_identity(user.id, "google", actor_id="system"),
        )
        self.assertCountEqual(["ok", "last_login_method"], results)
        account = db.get_account(user.id)
        identity_count = len(db.list_account_identities(user.id))
        self.assertTrue(account.password_login_enabled or identity_count > 0)

    def test_concurrent_identity_unlink_preserves_one_identity(self) -> None:
        user = db.create_account(
            name="sso-only", password="UnusedPassword-123", password_login_enabled=False,
        )
        self._add_identity(user.id, "google")
        self._add_identity(user.id, "telegram")
        results = self._race(
            lambda: sso_store.unlink_identity(user.id, "google", actor_id="system"),
            lambda: sso_store.unlink_identity(user.id, "telegram", actor_id="system"),
        )
        self.assertCountEqual(["ok", "last_login_method"], results)
        self.assertEqual(1, len(db.list_account_identities(user.id)))


if __name__ == "__main__":
    unittest.main()
