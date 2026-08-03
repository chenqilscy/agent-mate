"""Local App proxy must preserve the Server SSO authority boundary (WB-362)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from routers import auth as auth_router  # noqa: E402


class SsoProxyTest(unittest.TestCase):
    def test_only_server_configured_providers_are_exposed(self) -> None:
        providers = [{"id": "google", "label": "Google"}]
        with patch.object(auth_router.server_client, "sso_providers", return_value=providers):
            self.assertEqual(providers, auth_router.sso_providers()["providers"])

    def test_start_rejection_and_unreachable_are_not_local_fallbacks(self) -> None:
        body = auth_router.SsoStartBody(provider="google", invite_code="invite")
        with patch.object(
            auth_router.server_client, "sso_start",
            return_value=("rejected", {"code": 404, "detail": "provider_unavailable"}),
        ):
            with self.assertRaises(HTTPException) as rejected:
                auth_router.sso_start(body)
        self.assertEqual(404, rejected.exception.status_code)
        with patch.object(
            auth_router.server_client, "sso_start", return_value=("unreachable", None),
        ):
            with self.assertRaises(HTTPException) as unreachable:
                auth_router.sso_start(body)
        self.assertEqual(503, unreachable.exception.status_code)

    def test_completed_poll_mirrors_verified_server_account(self) -> None:
        remote = {
            "status": "completed", "token": "server-token", "expires_at": 12345,
            "account": {"id": "account-1", "name": "Alice", "plan": "体验版"},
        }
        mirrored = {"token": "server-token", "expires_at": 12345, "user": {"id": "account-1"}}
        with (
            patch.object(auth_router.server_client, "sso_poll", return_value=("ok", remote)),
            patch.object(auth_router, "_mirror_server_account", return_value=mirrored) as mirror,
        ):
            result = auth_router.sso_poll(
                auth_router.SsoPollBody(attempt_id="attempt", attempt_token="secret")
            )
        self.assertEqual("completed", result["status"])
        self.assertEqual("account-1", result["user"]["id"])
        mirror.assert_called_once_with("server-token", remote["account"], 12345)


if __name__ == "__main__":
    unittest.main()
