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
from config import settings  # noqa: E402
from routers import auth, sso  # noqa: E402


class SsoAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_policy = settings.SSO_REGISTRATION_POLICY
        self.old_limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
        self._close()
        settings.DB_PATH = Path(self.tmp.name) / "sso.db"
        settings.SSO_REGISTRATION_POLICY = "invite_only"
        settings.AUTH_RATE_LIMIT_PER_MINUTE = 100
        db.init_db()
        self.admin = db.create_account(
            name="admin", password="1111", email="admin@example.com"
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


if __name__ == "__main__":
    unittest.main()
