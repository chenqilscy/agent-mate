"""WB-401: Python emitters, TypeScript runtime allowlist and store cases stay aligned."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class SseEventContractTest(unittest.TestCase):
    def test_chat_event_names_match_frontend_runtime_and_exhaustive_store(self) -> None:
        events = (ROOT / "backend/agent/events.py").read_text(encoding="utf-8")
        chat = (ROOT / "backend/routers/chat.py").read_text(encoding="utf-8")
        types = (ROOT / "src/lib/types.ts").read_text(encoding="utf-8")
        store = (ROOT / "src/stores/chatStore.ts").read_text(encoding="utf-8")

        backend = set(re.findall(r'return sse\("([a-z_]+)"', events))
        backend.update(re.findall(r'events\.sse\("([a-z_]+)"', chat))
        block = re.search(r"SSE_EVENT_TYPES = \[(.*?)\] as const", types, re.S)
        self.assertIsNotNone(block)
        frontend = set(re.findall(r"'([a-z_]+)'", block.group(1)))  # type: ignore[union-attr]
        synthetic_block = re.search(r"CLIENT_EVENT_TYPES = \[(.*?)\] as const", types, re.S)
        self.assertIsNotNone(synthetic_block)
        synthetic = set(re.findall(r"'([a-z_]+)'", synthetic_block.group(1)))  # type: ignore[union-attr]
        handled = set(re.findall(r"case '([a-z_]+)'", store))

        self.assertEqual(backend, frontend)
        self.assertEqual(frontend | synthetic, handled)
        self.assertIn("const exhaustive: never = ev", store)
        self.assertIn(
            "checkedSSEEvent(event.type.slice(3), event.payload)",
            (ROOT / "src/lib/sse.ts").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
