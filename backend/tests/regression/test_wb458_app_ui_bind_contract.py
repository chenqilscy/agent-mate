"""WB-458: App UI must use the deterministic IPv4 loopback topology."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class AppUiBindContractTest(unittest.TestCase):
    def test_vite_and_proxies_use_ipv4_loopback(self) -> None:
        source = (ROOT / "vite.config.ts").read_text(encoding="utf-8")
        self.assertIn("host: '127.0.0.1'", source)
        self.assertIn("target: 'http://127.0.0.1:8101'", source)
        self.assertIn("target: 'http://127.0.0.1:8100'", source)
        self.assertNotIn("target: 'http://localhost:", source)

    def test_startup_output_uses_reachable_app_url(self) -> None:
        source = (ROOT / "run-stack.ps1").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8102", source)


if __name__ == "__main__":
    unittest.main()
