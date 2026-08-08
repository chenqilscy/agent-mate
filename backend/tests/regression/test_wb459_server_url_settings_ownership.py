"""WB-459: Server URL is owned only by application device settings."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import device_settings  # noqa: E402
import main  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402


class ServerUrlSettingsOwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_url = settings.AGENTMATE_SERVER_URL
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate.db"
        settings.AGENTMATE_SERVER_URL = ""
        db._local = threading.local()
        db.init_db()

    def tearDown(self) -> None:
        db.close_thread_connection()
        db._local = threading.local()
        settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url
        self.tmp.cleanup()

    def test_environment_cannot_supply_or_restore_server_url(self) -> None:
        item = device_settings.definition("collaboration.server_url")
        self.assertEqual("", item.env_name)
        self.assertFalse(item.environment_fallback)
        with patch.dict(os.environ, {"AGENTMATE_SERVER_URL": "https://env.invalid"}):
            self.assertEqual(("", "default"), device_settings.effective_with_source("collaboration.server_url"))
            device_settings.set_value(
                "collaboration.server_url", "http://127.0.0.1:8100", actor_id="local",
            )
            self.assertEqual(
                ("http://127.0.0.1:8100", "database"),
                device_settings.effective_with_source("collaboration.server_url"),
            )
            device_settings.clear_value("collaboration.server_url", actor_id="local")
            self.assertEqual(("", "default"), device_settings.effective_with_source("collaboration.server_url"))

    @patch("routers.asr.reset_model")
    @patch("agent.telemetry.reconfigure")
    def test_startup_restores_database_url_before_server_branch(self, _telemetry, _asr) -> None:
        db.set_device_setting("collaboration.server_url", "http://127.0.0.1:8100")
        settings.AGENTMATE_SERVER_URL = ""
        with (
            patch.object(main.local_agent_store, "init_db") as init_local_store,
            patch.object(main.db, "list_server_identities", return_value=[]),
            patch.object(main.db, "recover_stale_runs", return_value=[]),
            patch.object(main.orchestration_store, "ensure_tables"),
            patch.object(main.db, "migrate_skill_identities", return_value={"changed": 0, "dropped": 0}),
        ):
            main._startup()
        self.assertEqual("http://127.0.0.1:8100", settings.AGENTMATE_SERVER_URL)
        init_local_store.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
