"""WB-398: request-body cap must verify actual ASGI bytes, not just Content-Length."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from main import BodySizeLimitMiddleware  # noqa: E402


class JsonBodyStreamLimitTest(unittest.IsolatedAsyncioTestCase):
    async def _exercise(
        self, *, headers: list[tuple[bytes, bytes]], chunks: list[bytes],
        path: str = "/api/chat", limit: int = 8,
    ) -> tuple[bool, int | None, bytes]:
        called = False
        downstream_body = bytearray()
        sent: list[dict] = []
        incoming = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]

        async def app(_scope, receive, send) -> None:
            nonlocal called
            called = True
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    break
                downstream_body.extend(message.get("body") or b"")
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive() -> dict:
            return incoming.pop(0) if incoming else {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": path, "headers": headers}
        await BodySizeLimitMiddleware(app, limit)(scope, receive, send)
        status = next(
            (message["status"] for message in sent if message["type"] == "http.response.start"),
            None,
        )
        return called, status, bytes(downstream_body)

    async def test_declared_missing_and_forged_lengths_enforce_actual_limit(self) -> None:
        for headers in (
            [(b"content-length", b"9")],
            [],
            [(b"content-length", b"1")],
        ):
            called, status, _body = await self._exercise(headers=headers, chunks=[b"1234", b"56789"])
            self.assertFalse(called)
            self.assertEqual(413, status)

    async def test_exact_multiframe_limit_is_replayed_without_changes(self) -> None:
        called, status, body = await self._exercise(
            headers=[(b"content-length", b"8")], chunks=[b"123", b"45678"],
        )
        self.assertTrue(called)
        self.assertEqual(204, status)
        self.assertEqual(b"12345678", body)

    async def test_upload_route_keeps_its_independent_streaming_limit(self) -> None:
        called, status, body = await self._exercise(
            headers=[], chunks=[b"123456789"], path="/api/files/upload",
        )
        self.assertTrue(called)
        self.assertEqual(204, status)
        self.assertEqual(b"123456789", body)


if __name__ == "__main__":
    unittest.main()
