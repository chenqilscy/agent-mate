"""WB-460: Console handoff must resolve the real Server origin."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ConsoleHandoffContractTest(unittest.TestCase):
    def test_console_handoff_does_not_derive_from_relative_api_proxy(self) -> None:
        source = (ROOT / "src/lib/console.ts").read_text(encoding="utf-8")
        self.assertIn("serverConsoleBase", source)
        self.assertNotIn("serverApiBase", source)
        self.assertLess(source.index("window.open('about:blank'"), source.index("await serverConsoleBase()"))

    def test_console_base_comes_from_local_agent_runtime_status(self) -> None:
        source = (ROOT / "src/lib/channels.ts").read_text(encoding="utf-8")
        block = source[source.index("export async function serverConsoleBase"):source.index("export function resetServerApiBase")]
        self.assertIn("await refreshLocalAgentStatus()", block)
        self.assertIn("status?.server_api_url", block)
        self.assertIn("parsed = new URL(root)", block)
        self.assertNotIn("'/server-api'", block)

    def test_project_console_url_uses_same_resolver(self) -> None:
        source = (ROOT / "src/stores/serverStore.ts").read_text(encoding="utf-8")
        self.assertIn("serverConsoleBase", source)
        self.assertNotIn("base.replace(/\\/api$/", source)


if __name__ == "__main__":
    unittest.main()
