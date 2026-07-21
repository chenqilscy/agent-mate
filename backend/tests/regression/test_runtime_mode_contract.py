"""Plan/Ask mode normalization coverage (WB-272)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent.runtime import normalize_modes  # noqa: E402


class RuntimeModeContractTest(unittest.TestCase):
    def test_modes_are_mutually_exclusive_and_ask_wins(self) -> None:
        self.assertEqual((False, False), normalize_modes(False, False))
        self.assertEqual((True, False), normalize_modes(True, False))
        self.assertEqual((False, True), normalize_modes(False, True))
        self.assertEqual((False, True), normalize_modes(True, True))


if __name__ == "__main__":
    unittest.main()
