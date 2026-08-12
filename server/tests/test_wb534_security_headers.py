"""WB-534: Server-hosted Console and APIs carry a browser security baseline."""
from __future__ import annotations

import unittest
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

from security_headers import SecurityHeadersMiddleware  # noqa: E402


class SecurityHeadersTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        def console() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/api/health")
        def health() -> dict[str, bool]:
            return {"ok": True}

        self.app = app

    def test_console_and_api_receive_browser_security_headers(self) -> None:
        with TestClient(self.app, base_url="http://testserver") as client:
            for path in ("/", "/api/health"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("default-src 'self'", response.headers["content-security-policy"])
                self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(response.headers["x-frame-options"], "DENY")
                self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                self.assertNotIn("strict-transport-security", response.headers)

    def test_hsts_is_only_enabled_for_https_requests(self) -> None:
        with TestClient(self.app, base_url="https://server.example.test") as client:
            response = client.get("/")
        self.assertEqual(
            response.headers["strict-transport-security"],
            "max-age=31536000; includeSubDomains",
        )


if __name__ == "__main__":
    unittest.main()
