"""WB-486: Local Agent built-ins remain selectable without Server recommendations."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class BuiltinConnectorCardsContractTest(unittest.TestCase):
    def test_runtime_builtins_are_merged_into_connector_cards(self) -> None:
        source = (ROOT / "src" / "views" / "ExpertsView.tsx").read_text(encoding="utf-8")
        self.assertIn("const connectorCards = [", source)
        self.assertIn("item.source === 'builtin'", source)
        self.assertIn("!recommendationNames.has(item.name)", source)
        self.assertIn("connectorCards.length === 0 && localStatuses.length === 0", source)
        self.assertIn("connectorCards.map((connector)", source)


if __name__ == "__main__":
    unittest.main()
