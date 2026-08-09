"""WB-470: interactive high-risk grants support a bounded session scope."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.execution_policy import (
    ALLOW_ONCE_ANSWER,
    ALLOW_SESSION_ANSWER,
    DENY_ANSWER,
    TOOL_AUTHORIZATION_OPTIONS,
    ExecutionAuthorization,
    ToolAuthorizationDenied,
    clear_session_authorization,
    session_granted_permissions,
)
from routers import sessions as session_routes


class SessionToolAuthorizationTest(unittest.TestCase):
    owner_id = "wb470-owner"
    session_id = "wb470-session"

    def setUp(self) -> None:
        clear_session_authorization(self.owner_id, self.session_id)

    def tearDown(self) -> None:
        clear_session_authorization(self.owner_id, self.session_id)

    def test_prompt_contract_includes_once_session_and_deny(self) -> None:
        self.assertEqual(
            (ALLOW_ONCE_ANSWER, ALLOW_SESSION_ANSWER, DENY_ANSWER),
            TOOL_AUTHORIZATION_OPTIONS,
        )

    def test_allow_once_remains_bound_to_exact_call(self) -> None:
        auth = ExecutionAuthorization(owner_id=self.owner_id, session_id=self.session_id)
        permissions = ("process.execute", "host.unrestricted")
        first = {"command": "echo first"}
        second = {"command": "echo second"}

        self.assertEqual("confirm", auth.decision("run_command", first, permissions))
        auth.approve_once("run_command", first)
        self.assertEqual("allow", auth.decision("run_command", first, permissions))
        self.assertEqual("confirm", auth.decision("run_command", second, permissions))

    def test_session_grant_is_permission_owner_and_session_scoped(self) -> None:
        auth = ExecutionAuthorization(owner_id=self.owner_id, session_id=self.session_id)
        granted = ("workspace.read", "process.execute", "host.unrestricted")
        auth.approve_for_session(granted)

        self.assertEqual(
            frozenset({"process.execute", "host.unrestricted"}),
            session_granted_permissions(self.owner_id, self.session_id),
        )
        self.assertEqual(
            "allow",
            auth.decision("run_command", {"command": "echo later"}, granted),
        )
        self.assertEqual(
            "allow",
            auth.decision("another_process_tool", {"value": 1}, ("process.execute",)),
        )
        self.assertEqual(
            "allow",
            ExecutionAuthorization(self.owner_id, self.session_id).decision(
                "run_command", {"command": "echo next-run"}, granted,
            ),
        )
        self.assertEqual(
            "confirm",
            auth.decision("network_tool", {}, ("network.unrestricted",)),
        )
        self.assertEqual(
            "confirm",
            ExecutionAuthorization(self.owner_id, "another-session").decision(
                "run_command", {}, granted,
            ),
        )
        self.assertEqual(
            "confirm",
            ExecutionAuthorization("another-owner", self.session_id).decision(
                "run_command", {}, granted,
            ),
        )

    def test_clearing_session_revokes_the_temporary_grant(self) -> None:
        auth = ExecutionAuthorization(owner_id=self.owner_id, session_id=self.session_id)
        auth.approve_for_session(("process.execute",))
        clear_session_authorization(self.owner_id, self.session_id)
        self.assertEqual(
            "confirm", auth.decision("run_command", {}, ("process.execute",)),
        )

    def test_deleting_session_clears_its_temporary_grant(self) -> None:
        auth = ExecutionAuthorization(owner_id=self.owner_id, session_id=self.session_id)
        auth.approve_for_session(("process.execute",))
        with (
            patch.object(
                session_routes, "current_user",
                return_value=SimpleNamespace(id=self.owner_id),
            ),
            patch.object(session_routes.db, "get_session", return_value=object()),
            patch.object(session_routes.db, "delete_session") as delete_session,
        ):
            self.assertEqual(
                {"ok": True}, session_routes.delete_session(self.session_id),
            )
        delete_session.assert_called_once_with(self.session_id)
        self.assertEqual(
            frozenset(), session_granted_permissions(self.owner_id, self.session_id),
        )

    def test_background_execution_cannot_create_interactive_session_grant(self) -> None:
        auth = ExecutionAuthorization(
            owner_id=self.owner_id, session_id=self.session_id, source="background",
        )
        with self.assertRaises(ToolAuthorizationDenied):
            auth.approve_for_session(("process.execute",))


if __name__ == "__main__":
    unittest.main()
