"""WB-457: stale Server auth cannot strand Local Agent settings."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class LocalApiAuthContractTest(unittest.TestCase):
    def test_get_retries_once_but_writes_are_not_replayed(self) -> None:
        source = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
        get_block = re.search(
            r"async function get<.*?\n}\n\nasync function send", source, re.DOTALL,
        )
        send_block = re.search(
            r"async function send<.*?\n}\n\nexport interface AuthResult", source, re.DOTALL,
        )
        self.assertIsNotNone(get_block)
        self.assertIsNotNone(send_block)
        self.assertEqual(2, get_block.group(0).count("fetch("))
        self.assertEqual(1, send_block.group(0).count("fetch("))
        self.assertIn("r.status === 401 && invalidateStaleServerToken()", get_block.group(0))
        self.assertIn("r.status === 401", send_block.group(0))

    def test_auth_store_is_invalidated_without_reloading_the_app(self) -> None:
        api_source = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
        app_source = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
        self.assertIn("localStorage.removeItem(TOKEN_KEY)", api_source)
        self.assertIn("window.dispatchEvent(new Event(LOCAL_AUTH_INVALID_EVENT))", api_source)
        self.assertIn("window.addEventListener(LOCAL_AUTH_INVALID_EVENT, invalidate)", app_source)
        self.assertIn("useAuthStore.setState({ me: null, loggedIn: false })", app_source)


if __name__ == "__main__":
    unittest.main()
