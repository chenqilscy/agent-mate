import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class TauriContentSecurityPolicyTests(unittest.TestCase):
    def test_webview_uses_a_minimal_explicit_policy(self) -> None:
        config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        csp = config["app"]["security"]["csp"]
        self.assertIsInstance(csp, str)
        for directive in (
            "default-src 'self'",
            "connect-src 'self' ipc: http://ipc.localhost",
            "http://127.0.0.1:*",
            "https:",
            "wss:",
            "script-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "frame-ancestors 'none'",
        ):
            self.assertIn(directive, csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertNotIn("*;", csp)


if __name__ == "__main__":
    unittest.main()
