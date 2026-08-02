"""Provider output token cap governance (WB-364)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.runtime import _request_output_limit  # noqa: E402
from config import settings  # noqa: E402
from storage import db, model_governance  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ProviderOutputTokenCapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()

    def tearDown(self) -> None:
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_generation_uses_smallest_of_all_output_limits(self) -> None:
        self.assertEqual(4096, _request_output_limit(
            requested=20_000, model_cap=16_000, context_room=12_000, run_room=4096,
        ))
        self.assertEqual(8192, _request_output_limit(
            requested=0, model_cap=8192, context_room=190_000,
        ))

    def test_model_output_cap_is_persisted_in_run_snapshot(self) -> None:
        db.set_model_meta(
            LOCAL_USER_ID, "custom-ref", capabilities=["text", "tools"],
            input_cost=None, input_cost_cached=None, output_cost=None,
            context_window=200_000, currency=None, note=None,
            max_output_tokens=32_768,
        )
        snapshot = model_governance.build_run_snapshot(
            LOCAL_USER_ID, "custom-ref", "custom-model",
        )
        self.assertEqual(200_000, snapshot["context_window"])
        self.assertEqual(32_768, snapshot["max_output_tokens"])


if __name__ == "__main__":
    unittest.main()
