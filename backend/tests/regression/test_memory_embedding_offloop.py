"""WB-356: memory embedding/retrieval must not block the chat event loop."""
from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent import runtime  # noqa: E402


class MemoryEmbeddingOffloopTests(unittest.TestCase):
    def test_memory_prompt_runs_on_worker_thread_and_preserves_arguments(self) -> None:
        event_loop_thread = threading.get_ident()
        observed: dict[str, object] = {}

        def fake_prompt(owner_id: str, query_text: str, *, project_id: str | None) -> str:
            observed.update(
                thread=threading.get_ident(),
                owner_id=owner_id,
                query_text=query_text,
                project_id=project_id,
            )
            return "\n# memory"

        with (
            patch.object(runtime.memory, "build_memory_prompt", side_effect=fake_prompt),
            patch.object(runtime.db, "close_thread_connection") as close_connection,
        ):
            result = asyncio.run(runtime._build_memory_prompt("owner-1", "本轮问题", "project-1"))

        self.assertEqual("\n# memory", result)
        self.assertNotEqual(event_loop_thread, observed["thread"])
        self.assertEqual("owner-1", observed["owner_id"])
        self.assertEqual("本轮问题", observed["query_text"])
        self.assertEqual("project-1", observed["project_id"])
        close_connection.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
