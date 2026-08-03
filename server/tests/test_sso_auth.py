"""Federated SSO broker and public-auth hardening contracts (WB-362)."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import sso_protocol  # noqa: E402
import sso_store  # noqa: E402
import secret_crypto  # noqa: E402
from config import settings  # noqa: E402
from routers import auth, sso  # noqa: E402


class SsoAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_policy = settings.SSO_REGISTRATION_POLICY
        self.old_limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
        self.old_environment = settings.ENVIRONMENT
        self.old_encryption_key = settings.SSO_SECRET_ENCRYPTION_KEY
        self.old_encryption_key_id = settings.SSO_SECRET_ENCRYPTION_KEY_ID
        self.old_previous_keys = settings.SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS
        self.old_local_key_path = settings.SSO_LOCAL_KEY_PATH
        self.old_public_base = settings.SSO_PUBLIC_BASE_URL
        self._close()
        settings.DB_PATH = Path(self.tmp.name) / "sso.db"
        settings.SSO_REGISTRATION_POLICY = "invite_only"
        settings.AUTH_RATE_LIMIT_PER_MINUTE = 100
        settings.ENVIRONMENT = "development"
        settings.SSO_SECRET_ENCRYPTION_KEY = ""
        settings.SSO_SECRET_ENCRYPTION_KEY_ID = "primary"
        settings.SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS = "{}"
        settings.SSO_LOCAL_KEY_PATH = ""
        settings.SSO_PUBLIC_BASE_URL = "http://127.0.0.1:8100"
        db.init_db()
        self.admin = db.create_account(
            name="admin", password="1111", email="admin@example.com",
            is_platform_admin=True,
        )
        self.admin_token = db.create_token(self.admin.id)[0]
        app = FastAPI()
        app.include_router(auth.router)
        app.include_router(sso.router)
        self.client = TestClient(app)
        self.admin_auth = {"Authorization": f"Bearer {self.admin_token}"}

    def tearDown(self) -> None:
        self.client.close()
        self._close()
        settings.DB_PATH = self.old_db
        settings.SSO_REGISTRATION_POLICY = self.old_policy
        settings.AUTH_RATE_LIMIT_PER_MINUTE = self.old_limit
        settings.ENVIRONMENT = self.old_environment
        settings.SSO_SECRET_ENCRYPTION_KEY = self.old_encryption_key
        settings.SSO_SECRET_ENCRYPTION_KEY_ID = self.old_encryption_key_id
        settings.SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS = self.old_previous_keys
        settings.SSO_LOCAL_KEY_PATH = self.old_local_key_path
        settings.SSO_PUBLIC_BASE_URL = self.old_public_base
        self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _configure(self, provider: str = "google") -> None:
        response = self.client.put(
            f"/api/admin/sso/providers/{provider}", headers=self.admin_auth,
            json={"enabled": True, "client_id": f"{provider}-client", "client_secret": "top-secret"},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertNotIn("client_secret", response.text)
        stored = db.get_conn().execute(
            "SELECT client_secret FROM sso_provider_configs WHERE provider=?", (provider,),
        ).fetchone()["client_secret"]
        self.assertTrue(secret_crypto.is_encrypted(stored))
        self.assertNotIn("top-secret", stored)

    def _start(self, provider: str = "google", invite_code: str = "", headers=None) -> dict:
        response = self.client.post(
            "/api/auth/sso/start", headers=headers or {},
            json={"provider": provider, "invite_code": invite_code},
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    def test_invited_login_state_replay_secret_hiding_and_hashed_token(self) -> None:
        self.assertEqual([], self.client.get("/api/auth/sso/providers").json()["providers"])
        member = db.create_account(name="member", password="1111")
        member_token = db.create_token(member.id)[0]
        denied = self.client.get(
            "/api/admin/sso/providers",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        self.assertEqual(403, denied.status_code)
        self._configure()
        audit_text = self.client.get(
            "/api/admin/sso/audit", headers=self.admin_auth,
        ).text
        self.assertIn("client_secret_rotated", audit_text)
        self.assertNotIn("top-secret", audit_text)
        public = self.client.get("/api/auth/sso/providers").json()["providers"]
        self.assertEqual([{"id": "google", "label": "Google"}], public)
        invite = self.client.post(
            "/api/admin/sso/signup-invites", headers=self.admin_auth,
            json={"ttl_seconds": 600},
        ).json()["code"]
        stored_invite = db.get_conn().execute(
            "SELECT code_hash FROM sso_signup_invites"
        ).fetchone()["code_hash"]
        self.assertNotEqual(invite, stored_invite)
        started = self._start(invite_code=invite)
        query = parse_qs(urlparse(started["auth_url"]).query)
        self.assertIn("code_challenge", query)
        self.assertIn("nonce", query)
        state = query["state"][0]

        identity = {"subject": "google-sub-1", "email": "new@example.com", "name": "New User"}
        with patch.object(sso_protocol, "exchange_identity", return_value=identity):
            callback = self.client.get(
                "/api/auth/sso/google/callback", params={"state": state, "code": "real-code"},
            )
        self.assertEqual(200, callback.status_code, callback.text)
        replay = self.client.get(
            "/api/auth/sso/google/callback", params={"state": state, "code": "real-code"},
        )
        self.assertEqual(400, replay.status_code)
        wrong = self.client.post(
            "/api/auth/sso/poll",
            json={"attempt_id": started["attempt_id"], "attempt_token": "wrong"},
        )
        self.assertEqual(401, wrong.status_code)
        complete = self.client.post(
            "/api/auth/sso/poll",
            json={"attempt_id": started["attempt_id"], "attempt_token": started["attempt_token"]},
        )
        self.assertEqual(200, complete.status_code, complete.text)
        body = complete.json()
        self.assertEqual("completed", body["status"])
        self.assertEqual("new@example.com", body["account"]["email"])
        stored = db.get_conn().execute(
            "SELECT token FROM server_tokens WHERE account_id=?", (body["account"]["id"],)
        ).fetchone()["token"]
        self.assertTrue(stored.startswith("sha256:"))
        self.assertNotEqual(body["token"], stored)
        self.assertEqual(body["account"]["id"], db.account_id_for_token(body["token"]))
        actions = {item["action"] for item in db.list_auth_audit(account_id=body["account"]["id"])}
        self.assertTrue({"account_registered_sso", "sso_identity_linked", "sso_login"} <= actions)
        consumed = self.client.post(
            "/api/auth/sso/poll",
            json={"attempt_id": started["attempt_id"], "attempt_token": started["attempt_token"]},
        )
        self.assertEqual(409, consumed.status_code)

    def test_explicit_link_required_link_permissions_and_identity_conflict(self) -> None:
        self._configure()
        local = db.create_account(name="local", password="1111", email="same@example.com")
        local_token = db.create_token(local.id)[0]
        settings.SSO_REGISTRATION_POLICY = "open"
        started = self._start()
        state = parse_qs(urlparse(started["auth_url"]).query)["state"][0]
        with patch.object(sso_protocol, "exchange_identity", return_value={
            "subject": "subject-same-email", "email": "same@example.com", "name": "Collision",
        }):
            self.client.get("/api/auth/sso/google/callback", params={"state": state, "code": "code"})
        failed = self.client.post(
            "/api/auth/sso/poll",
            json={"attempt_id": started["attempt_id"], "attempt_token": started["attempt_token"]},
        ).json()
        self.assertEqual("explicit_link_required", failed["error_code"])

        unauth = self.client.post(
            "/api/auth/sso/start", json={"provider": "google", "mode": "link"},
        )
        self.assertEqual(401, unauth.status_code)
        linked = self.client.post(
            "/api/auth/sso/start", headers={"Authorization": f"Bearer {local_token}"},
            json={"provider": "google", "mode": "link"},
        ).json()
        state = parse_qs(urlparse(linked["auth_url"]).query)["state"][0]
        with patch.object(sso_protocol, "exchange_identity", return_value={
            "subject": "subject-same-email", "email": "same@example.com", "name": "Local",
        }):
            self.client.get("/api/auth/sso/google/callback", params={"state": state, "code": "code"})
        result = self.client.post(
            "/api/auth/sso/poll",
            json={"attempt_id": linked["attempt_id"], "attempt_token": linked["attempt_token"]},
        ).json()
        self.assertEqual(local.id, result["account"]["id"])
        actions = {item["action"] for item in db.list_auth_audit(account_id=local.id)}
        self.assertTrue({"sso_identity_linked", "sso_login"} <= actions)
        other = db.create_account(name="other", password="1111")
        other_token = db.create_token(other.id)[0]
        conflict = self.client.post(
            "/api/auth/sso/start", headers={"Authorization": f"Bearer {other_token}"},
            json={"provider": "google", "mode": "link"},
        ).json()
        state = parse_qs(urlparse(conflict["auth_url"]).query)["state"][0]
        with patch.object(sso_protocol, "exchange_identity", return_value={
            "subject": "subject-same-email", "email": "", "name": "Other",
        }):
            self.client.get("/api/auth/sso/google/callback", params={"state": state, "code": "code"})
        conflict_result = self.client.post(
            "/api/auth/sso/poll",
            json={"attempt_id": conflict["attempt_id"], "attempt_token": conflict["attempt_token"]},
        ).json()
        self.assertEqual("identity_already_linked", conflict_result["error_code"])
        unlinked = self.client.delete(
            "/api/auth/identities/google",
            headers={"Authorization": f"Bearer {result['token']}"},
        )
        self.assertEqual(200, unlinked.status_code, unlinked.text)
        self.assertIn(
            "sso_identity_unlinked",
            {item["action"] for item in db.list_auth_audit(account_id=local.id)},
        )

    def test_oidc_signature_nonce_wechat_subject_password_upgrade_and_rate_limit(self) -> None:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com", "aud": "google-client", "sub": "subject",
            "iat": now, "exp": now + 300, "nonce": "nonce", "email": "a@example.com",
            "email_verified": True,
        }
        good = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "one"})
        bad = jwt.encode(claims, wrong_private, algorithm="RS256", headers={"kid": "one"})
        key_client = SimpleNamespace(get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private.public_key()))
        with patch.object(jwt, "PyJWKClient", return_value=key_client):
            identity = sso_protocol._verify_oidc(
                "google", good, {"client_id": "google-client"}, "nonce"
            )
            self.assertEqual("subject", identity["subject"])
            with self.assertRaises(jwt.InvalidSignatureError):
                sso_protocol._verify_oidc("google", bad, {"client_id": "google-client"}, "nonce")
            with self.assertRaisesRegex(ValueError, "invalid_nonce"):
                sso_protocol._verify_oidc("google", good, {"client_id": "google-client"}, "wrong")

        legacy = hashlib.pbkdf2_hmac("sha256", b"1111", bytes.fromhex("00" * 16), 1000).hex()
        db.get_conn().execute(
            "UPDATE accounts SET password_hash=? WHERE id=?",
            (f"pbkdf2$1000${'00' * 16}${legacy}", self.admin.id),
        )
        db.get_conn().commit()
        login = self.client.post("/api/auth/login", json={"name": "admin", "password": "1111"})
        self.assertEqual(200, login.status_code, login.text)
        upgraded = db.get_account_by_name("admin")
        self.assertTrue(upgraded and upgraded[1].startswith("scrypt$"))

        settings.AUTH_RATE_LIMIT_PER_MINUTE = 1
        first = self.client.post("/api/auth/login", json={"name": "rate", "password": "bad"})
        second = self.client.post("/api/auth/login", json={"name": "rate", "password": "bad"})
        self.assertEqual(401, first.status_code)
        self.assertEqual(429, second.status_code)

    def test_three_provider_protocol_contracts_and_wechat_exchange(self) -> None:
        self._configure("wechat")
        self._configure("telegram")
        wechat = self._start("wechat")
        telegram = self._start("telegram")
        wechat_query = parse_qs(urlparse(wechat["auth_url"]).query)
        telegram_query = parse_qs(urlparse(telegram["auth_url"]).query)
        self.assertEqual(["snsapi_login"], wechat_query["scope"])
        self.assertNotIn("code_challenge", wechat_query)
        self.assertEqual(["S256"], telegram_query["code_challenge_method"])
        self.assertEqual("oauth.telegram.org", urlparse(telegram["auth_url"]).netloc)

        class Response:
            def __init__(self, body: dict) -> None:
                self.body = body

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return self.body

        config = sso_store.provider_config("wechat")
        attempt = {
            "code_verifier": "unused", "nonce": "unused",
        }
        with patch.object(sso_protocol.httpx, "get", side_effect=[
            Response({"access_token": "access", "openid": "openid-1"}),
            Response({"openid": "openid-1", "unionid": "union-1", "nickname": "微信用户"}),
        ]):
            identity = sso_protocol.exchange_identity("wechat", config or {}, attempt, "code")
        self.assertEqual("union-1", identity["subject"])
        self.assertEqual("微信用户", identity["name"])

    def test_plaintext_secret_migration_and_production_key_gate(self) -> None:
        db.get_conn().execute(
            "INSERT INTO sso_provider_configs "
            "(provider,enabled,client_id,client_secret,updated_by,updated_at) "
            "VALUES ('google',1,'client','legacy-plaintext','legacy',?)",
            (time.time(),),
        )
        db.get_conn().commit()
        self.assertEqual(1, sso_store.migrate_plaintext_provider_secrets())
        stored = db.get_conn().execute(
            "SELECT client_secret FROM sso_provider_configs WHERE provider='google'"
        ).fetchone()["client_secret"]
        self.assertTrue(secret_crypto.is_encrypted(stored))
        self.assertEqual("legacy-plaintext", sso_store.provider_config("google")["client_secret"])
        audit = sso_store.list_provider_audit()
        self.assertEqual("client_secret_encrypted_migration", audit[0]["action"])
        self.assertNotIn("legacy-plaintext", str(audit))

        settings.ENVIRONMENT = "production"
        settings.SSO_SECRET_ENCRYPTION_KEY = ""
        with self.assertRaises(secret_crypto.SecretKeyUnavailable):
            sso_store.set_provider(
                "wechat", enabled=True, client_id="client",
                client_secret="production-secret", updated_by=self.admin.id,
            )

    def test_provider_readiness_requires_public_https_for_external_acceptance(self) -> None:
        self._configure("google")
        local = self.client.get(
            "/api/admin/sso/readiness", headers=self.admin_auth,
        ).json()
        google = next(item for item in local["providers"] if item["id"] == "google")
        self.assertFalse(local["public_https"])
        self.assertFalse(google["ready_for_external_test"])

        settings.SSO_PUBLIC_BASE_URL = "https://agentmate.example.com"
        public = self.client.get(
            "/api/admin/sso/readiness", headers=self.admin_auth,
        ).json()
        google = next(item for item in public["providers"] if item["id"] == "google")
        self.assertTrue(google["ready_for_external_test"])
        self.assertEqual(
            "https://agentmate.example.com/api/auth/sso/google/callback",
            google["callback_url"],
        )

    def test_keyring_rotation_and_readiness_decryption_probe(self) -> None:
        settings.SSO_SECRET_ENCRYPTION_KEY = "old-secret"
        settings.SSO_SECRET_ENCRYPTION_KEY_ID = "old"
        self._configure("google")
        old_cipher = db.get_conn().execute(
            "SELECT client_secret FROM sso_provider_configs WHERE provider='google'"
        ).fetchone()["client_secret"]
        self.assertEqual("old", secret_crypto.key_id(old_cipher))

        settings.SSO_SECRET_ENCRYPTION_KEY = "new-secret"
        settings.SSO_SECRET_ENCRYPTION_KEY_ID = "new"
        settings.SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS = '{"old":"old-secret"}'
        rotated = self.client.post(
            "/api/admin/sso/rotate-encryption", headers=self.admin_auth,
        )
        self.assertEqual(200, rotated.status_code, rotated.text)
        self.assertEqual(1, rotated.json()["rotated"])
        new_cipher = db.get_conn().execute(
            "SELECT client_secret FROM sso_provider_configs WHERE provider='google'"
        ).fetchone()["client_secret"]
        self.assertEqual("new", secret_crypto.key_id(new_cipher))
        self.assertEqual("top-secret", sso_store.provider_config("google")["client_secret"])

        settings.SSO_SECRET_ENCRYPTION_KEY = "wrong-secret"
        settings.SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS = "{}"
        readiness = sso_store.provider_readiness()
        google = next(item for item in readiness["providers"] if item["id"] == "google")
        self.assertIn("secret_decryption_failed", google["blockers"])
        self.assertFalse(readiness["ready"])


if __name__ == "__main__":
    unittest.main()
