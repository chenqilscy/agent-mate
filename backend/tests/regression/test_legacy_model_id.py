"""Legacy model-selection parsing coverage (WB-274)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.runtime import parse_legacy_model_id  # noqa: E402


class LegacyModelIdTest(unittest.TestCase):
    def test_label_only_removes_the_first_colon_prefix(self) -> None:
        self.assertEqual("vendor/model:free", parse_legacy_model_id("Display:vendor/model:free"))
        self.assertEqual("real-id", parse_legacy_model_id("Display:real-id"))

    def test_bare_provider_path_with_variant_is_preserved(self) -> None:
        self.assertEqual("vendor/model:free", parse_legacy_model_id("vendor/model:free"))

    def test_non_legacy_value_is_not_claimed(self) -> None:
        self.assertIsNone(parse_legacy_model_id("plain-model"))


if __name__ == "__main__":
    unittest.main()
