"""WB-546 raw ingress is bounded before downstream body buffering."""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

from config import settings  # noqa: E402
from request_limits import RawIngressBodyLimitMiddleware, SIGNED_INGRESS_MAX_BYTES  # noqa: E402


class RequestBodyLimitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_part_size = settings.ASSET_UPLOAD_PART_BYTES

    def tearDown(self) -> None:
        settings.ASSET_UPLOAD_PART_BYTES = self.old_part_size

    @staticmethod
    def _scope(method: str, path: str, content_length: str = "") -> dict:
        headers = [] if not content_length else [(b"content-length", content_length.encode("ascii"))]
        return {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": b"", "headers": headers, "client": ("test", 1),
            "server": ("testserver", 80),
        }

    @staticmethod
    def _run(scope: dict, frames: list[dict]) -> tuple[bool, bytes, list[dict]]:
        called = False
        received = bytearray()
        sent: list[dict] = []

        async def downstream(_scope, receive, send) -> None:
            nonlocal called
            called = True
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    break
                received.extend(message.get("body") or b"")
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        queue = list(frames)

        async def receive() -> dict:
            return queue.pop(0) if queue else {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            sent.append(message)

        asyncio.run(RawIngressBodyLimitMiddleware(downstream)(scope, receive, send))
        return called, bytes(received), sent

    def test_chunked_webhook_exceeding_limit_is_rejected_before_route(self) -> None:
        frames = [
            {"type": "http.request", "body": b"a" * 32768, "more_body": True},
            {"type": "http.request", "body": b"b" * 32768, "more_body": True},
            {"type": "http.request", "body": b"c", "more_body": False},
        ]
        called, _body, sent = self._run(
            self._scope("POST", "/api/webhooks/automations/hook-1"), frames,
        )
        self.assertFalse(called)
        self.assertEqual(413, sent[0]["status"])

    def test_forged_small_content_length_cannot_bypass_asset_part_limit(self) -> None:
        settings.ASSET_UPLOAD_PART_BYTES = 8
        frames = [{"type": "http.request", "body": b"123456789", "more_body": False}]
        called, _body, sent = self._run(
            self._scope("PUT", "/api/assets/uploads/u-1/parts/0", "1"), frames,
        )
        self.assertFalse(called)
        self.assertEqual(413, sent[0]["status"])

    def test_boundary_payload_is_replayed_without_mutation(self) -> None:
        expected = b"a" * 32768 + b"b" * 32768
        frames = [
            {"type": "http.request", "body": expected[:32768], "more_body": True},
            {"type": "http.request", "body": expected[32768:], "more_body": False},
        ]
        called, body, sent = self._run(
            self._scope("POST", "/api/relay/events", str(SIGNED_INGRESS_MAX_BYTES)), frames,
        )
        self.assertTrue(called)
        self.assertEqual(expected, body)
        self.assertEqual(204, sent[0]["status"])

    def test_unrelated_json_and_get_routes_are_not_prebuffered(self) -> None:
        frames = [{"type": "http.request", "body": b"{}", "more_body": False}]
        called, body, sent = self._run(self._scope("POST", "/api/projects"), frames)
        self.assertTrue(called)
        self.assertEqual(b"{}", body)
        self.assertEqual(204, sent[0]["status"])


if __name__ == "__main__":
    unittest.main()
