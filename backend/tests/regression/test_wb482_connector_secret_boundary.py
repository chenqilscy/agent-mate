"""WB-482: owner-created connectors cannot read Local Agent host secrets."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import mcp_client  # noqa: E402


class ConnectorSecretBoundaryTest(unittest.TestCase):
    def test_custom_connector_never_falls_back_to_process_environment(self) -> None:
        spec = {"_instance_id": "custom-1", "secret_keys": ["REVIEW_HOST_SECRET"]}
        with patch.dict(os.environ, {"REVIEW_HOST_SECRET": "must-not-leak"}, clear=False), patch(
            "local_agent_store.get_connector_secret", return_value=None,
        ):
            value = mcp_client._credential("owner-a", "Custom", spec, "REVIEW_HOST_SECRET")
        self.assertEqual("", value)

    def test_trusted_catalog_connector_keeps_declared_environment_fallback(self) -> None:
        with patch.dict(os.environ, {"REVIEW_CATALOG_SECRET": "catalog-value"}, clear=False), patch(
            "local_agent_store.get_builtin_connector_secret", return_value=None,
        ):
            value = mcp_client._credential(
                "owner-a", "Trusted", {"requires": ["REVIEW_CATALOG_SECRET"]},
                "REVIEW_CATALOG_SECRET",
            )
        self.assertEqual("catalog-value", value)


if __name__ == "__main__":
    unittest.main()
