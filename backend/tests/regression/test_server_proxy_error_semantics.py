"""WB-393: Server proxy preserves authoritative rejection and outage semantics."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from routers import server as server_router  # noqa: E402
import server_client  # noqa: E402


def response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload)


class ServerProxyErrorSemanticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_url = settings.AGENTMATE_SERVER_URL
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"

    def tearDown(self) -> None:
        settings.AGENTMATE_SERVER_URL = self.old_url

    def test_strict_transport_preserves_4xx_for_every_http_verb(self) -> None:
        cases = [
            ("get", server_client._get, ("/read", "token"), 403, "forbidden"),
            ("post", server_client._post, ("/create", "token", {}), 409, "archived"),
            ("patch", server_client._patch, ("/update", "token", {}), 422, [{"msg": "invalid"}]),
            ("delete", server_client._delete, ("/delete", "token"), 404, "missing"),
        ]
        for verb, call, args, status, detail in cases:
            with self.subTest(verb=verb), patch.object(
                server_client.httpx, verb, return_value=response(status, {"detail": detail}),
            ), self.assertRaises(HTTPException) as rejected:
                call(*args, strict=True)
            self.assertEqual(status, rejected.exception.status_code)
            self.assertEqual(detail, rejected.exception.detail)

    def test_background_mode_and_unavailable_server_remain_guarded(self) -> None:
        with patch.object(
            server_client.httpx, "post", return_value=response(409, {"detail": "conflict"}),
        ):
            self.assertIsNone(server_client._post("/background", "token", {}))

        with patch.object(
            server_client.httpx, "post", return_value=response(500, {"detail": "broken"}),
        ):
            self.assertIsNone(server_client._post("/write", "token", {}, strict=True))

        with patch.object(server_client.httpx, "post", side_effect=httpx.ConnectError("offline")):
            self.assertIsNone(server_client._post("/write", "token", {}, strict=True))

    def test_comment_and_presence_reads_do_not_forge_empty_success(self) -> None:
        with (
            patch.object(server_router.server_client, "server_enabled", return_value=True),
            self.assertRaises(HTTPException) as missing_identity,
        ):
            server_router.server_comments("project-1", authorization="")
        self.assertEqual(401, missing_identity.exception.status_code)
        self.assertEqual("server identity required", missing_identity.exception.detail)

        with (
            patch.object(server_router.server_client, "server_enabled", return_value=True),
            patch.object(server_router.server_client, "list_comments", return_value=None),
            self.assertRaises(HTTPException) as comments,
        ):
            server_router.server_comments("project-1", authorization="Bearer token")
        self.assertEqual(503, comments.exception.status_code)

        with (
            patch.object(server_router.server_client, "server_enabled", return_value=True),
            patch.object(server_router.server_client, "list_presence", return_value=None),
            self.assertRaises(HTTPException) as presence,
        ):
            server_router.server_presence("project-1", authorization="Bearer token")
        self.assertEqual(503, presence.exception.status_code)

        with (
            patch.object(server_router.server_client, "server_enabled", return_value=True),
            patch.object(
                server_router.server_client, "list_comments",
                side_effect=HTTPException(403, "Viewer is read-only"),
            ),
            self.assertRaises(HTTPException) as forbidden,
        ):
            server_router.server_comments("project-1", authorization="Bearer token")
        self.assertEqual(403, forbidden.exception.status_code)


if __name__ == "__main__":
    unittest.main()
