"""AgentMate accounts must always originate from Server (WB-314)."""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth import deps  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import me as me_router  # noqa: E402
from routers import server as server_router  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ServerAccountAuthorityTest(unittest.TestCase):
    def test_login_mirrors_server_user_payload_shape(self) -> None:
        mirrored = {"token": "server-token", "user": {"id": "account-1"}}
        with (
            patch.object(auth_router.server_client, "server_enabled", return_value=True),
            patch.object(
                auth_router.server_client, "server_login_ex", return_value=("ok", {
                    "token": "server-token", "expires_at": 12345,
                    "user": {"id": "account-1", "name": "admin", "plan": "体验版"},
                }),
            ),
            patch.object(auth_router, "_mirror_server_account", return_value=mirrored) as mirror,
        ):
            result = auth_router.login(auth_router.LoginBody(name="admin", password="admin123"))

        self.assertEqual(mirrored, result)
        mirror.assert_called_once_with(
            "server-token",
            {"id": "account-1", "name": "admin", "plan": "体验版"},
            12345,
        )

    def test_unconfigured_server_cannot_create_or_login_local_account(self) -> None:
        with (
            patch.object(auth_router.server_client, "server_enabled", return_value=False),
            patch.object(auth_router.db, "create_user") as create_user,
            patch.object(auth_router.db, "get_user_by_name") as get_local_user,
        ):
            with self.assertRaises(HTTPException) as registered:
                auth_router.register(auth_router.RegisterBody(name="alice", password="secret"))
            with self.assertRaises(HTTPException) as logged_in:
                auth_router.login(auth_router.LoginBody(name="alice", password="secret"))

        self.assertEqual(503, registered.exception.status_code)
        self.assertEqual(503, logged_in.exception.status_code)
        create_user.assert_not_called()
        get_local_user.assert_not_called()

    def test_unreachable_server_never_falls_back_to_local_password(self) -> None:
        with (
            patch.object(auth_router.server_client, "server_enabled", return_value=True),
            patch.object(
                auth_router.server_client, "server_login_ex",
                return_value=("unreachable", None),
            ),
            patch.object(auth_router.db, "get_user_by_name") as get_local_user,
            patch.object(auth_router.db, "create_token") as create_token,
        ):
            with self.assertRaises(HTTPException) as raised:
                auth_router.login(auth_router.LoginBody(name="legacy", password="secret"))

        self.assertEqual(503, raised.exception.status_code)
        get_local_user.assert_not_called()
        create_token.assert_not_called()

    def test_cached_server_token_still_resolves_offline(self) -> None:
        with (
            patch.object(deps.db, "is_token_revocation_pending", return_value=False),
            patch.object(deps.db, "cached_server_user", return_value="server-account") as cached,
            patch.object(deps.server_client, "verify_token_state") as verify_remote,
        ):
            self.assertEqual("server-account", deps.resolve_token_to_user_id("server-token"))

        cached.assert_called_once_with(
            "server-token", max_validation_age=deps.settings.SERVER_TOKEN_VALIDATION_TTL_SECONDS,
        )
        verify_remote.assert_not_called()

    def test_legacy_local_token_is_not_an_account_identity(self) -> None:
        with (
            patch.object(deps.db, "is_token_revocation_pending", return_value=False),
            patch.object(deps.db, "cached_server_user", return_value=None),
        ):
            self.assertIsNone(deps.resolve_token_to_user_id("legacy-local-token"))

    def test_stale_cache_introspects_and_authoritative_rejection_revokes(self) -> None:
        with (
            patch.object(deps.db, "is_token_revocation_pending", return_value=False),
            patch.object(deps.server_client, "verify_token_state", return_value=("invalid", None)),
            patch.object(deps.db, "revoke_cached_server_token") as revoke,
        ):
            self.assertIsNone(deps.resolve_via_server("revoked-token"))
        revoke.assert_called_once_with("revoked-token")

    def test_server_outage_uses_only_bounded_offline_cache(self) -> None:
        with (
            patch.object(deps.db, "is_token_revocation_pending", return_value=False),
            patch.object(deps.server_client, "verify_token_state", return_value=("unavailable", None)),
            patch.object(deps.db, "cached_server_user", return_value="server-account") as cached,
        ):
            self.assertEqual("server-account", deps.resolve_via_server("offline-token"))
        cached.assert_called_once_with(
            "offline-token", max_validation_age=deps.settings.SERVER_TOKEN_OFFLINE_GRACE_SECONDS,
        )

    def test_server_status_restores_only_cached_server_identity(self) -> None:
        cached_account = SimpleNamespace(id="server-account", name="Alice")
        with (
            patch.object(server_router.server_client, "server_enabled", return_value=False),
            patch.object(server_router.db, "cached_server_token_status", return_value={
                "user_id": "server-account", "expires_at": 9999999999.0,
                "validated_at": 9999999999.0,
            }),
            patch.object(server_router.db, "cached_server_user", return_value="server-account"),
            patch.object(server_router.db, "get_user", return_value=cached_account),
            patch.object(server_router.server_client, "verify_token_state") as verify_remote,
        ):
            result = server_router.server_status("Bearer server-token")

        self.assertFalse(result["enabled"])
        self.assertEqual({"account_id": "server-account", "name": "Alice"}, result["linked"])
        self.assertEqual("offline_grace", result["auth_state"])
        self.assertGreaterEqual(result["offline_grace_remaining_seconds"], 0)
        verify_remote.assert_not_called()

    def test_server_status_never_treats_guest_import_link_as_login(self) -> None:
        with (
            patch.object(server_router.server_client, "server_enabled", return_value=True),
            patch.object(server_router.db, "get_server_link") as legacy_import_link,
        ):
            result = server_router.server_status("")

        self.assertIsNone(result["linked"])
        self.assertEqual("disconnected", result["auth_state"])
        legacy_import_link.assert_not_called()

    def test_me_exposes_real_server_authentication_state(self) -> None:
        guest = SimpleNamespace(
            id=LOCAL_USER_ID, name="Guest", role=SimpleNamespace(value="Owner"), plan="体验版",
        )
        account = SimpleNamespace(
            id="server-account", name="Alice", role=SimpleNamespace(value="Owner"), plan="专业版",
        )
        with (
            patch.object(me_router, "current_user", return_value=guest),
            patch.object(me_router.model_governance, "account_has_model_configuration", return_value=False),
        ):
            self.assertFalse(me_router.get_me()["authenticated"])
        with (
            patch.object(me_router, "current_user", return_value=account),
            patch.object(me_router.model_governance, "account_has_model_configuration", return_value=False),
        ):
            self.assertTrue(me_router.get_me()["authenticated"])


if __name__ == "__main__":
    unittest.main()
