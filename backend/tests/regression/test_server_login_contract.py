"""Server login keeps its public `register` JSON field without model warnings (WB-288)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from routers import server as server_router  # noqa: E402


class ServerLoginContractTest(unittest.TestCase):
    def test_register_alias_is_forwarded_without_shadowing_base_model(self) -> None:
        body = server_router.ServerLoginBody.model_validate({
            "name": " alice ", "password": "secret", "register": True,
        })
        self.assertTrue(body.create_account)
        with (
            patch.object(server_router.server_client, "server_enabled", return_value=True),
            patch.object(server_router.server_client, "server_login", return_value={
                "token": "token", "account": {"id": "alice"},
            }) as login,
        ):
            result = server_router.server_login(body)
        self.assertEqual("token", result["token"])
        login.assert_called_once_with("alice", "secret", True)


if __name__ == "__main__":
    unittest.main()
