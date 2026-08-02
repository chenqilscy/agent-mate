"""WB-353 local-first portfolio aggregation and one-request Server fallback."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import project_health_service  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


def health(status: str, *, blocked: int = 0) -> dict:
    return {
        "status": status, "source": "server", "stale": False,
        "computed_at": 10, "as_of": "2026-08-02",
        "summary": {"blocked_tasks": blocked}, "reasons": [], "milestones": [],
    }


class ProjectHealthPortfolioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = settings.AGENTMATE_SERVER_URL
        self._close()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        db.init_db()
        self.local = db.create_project(owner_id=LOCAL_USER_ID, name="local")
        db.create_work_item(
            project_id=self.local.id, owner_id=LOCAL_USER_ID, title="blocked",
            status="paused", due_date="2000-01-01",
        )
        db.mirror_server_project(
            id="server-project", name="server", owner_id=LOCAL_USER_ID,
            instruction="", created_at=1, updated_at=2,
        )

    def tearDown(self) -> None:
        self._close()
        settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url
        self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close(); db._local.conn = None

    def test_mixed_portfolio_calls_server_once_filters_remote_and_replays_cache(self) -> None:
        remote = {
            "items": [
                {"project": {"id": "server-project"}, "health": health("critical", blocked=2)},
                {"project": {"id": "not-accessible"}, "health": health("critical", blocked=99)},
            ],
        }
        with patch.object(db, "get_server_identity", return_value="owner-token"), patch.object(
            project_health_service.server_client, "get_project_health_portfolio", return_value=remote,
        ) as get_portfolio, patch.object(
            project_health_service.server_client, "get_project_health",
        ) as get_single:
            result = project_health_service.resolve_project_health_portfolio(LOCAL_USER_ID)

        get_portfolio.assert_called_once_with("owner-token")
        get_single.assert_not_called()
        self.assertEqual("mixed", result["source"])
        self.assertEqual(["server-project", self.local.id], [row["project"]["id"] for row in result["items"]])
        self.assertEqual(2, result["summary"]["total_projects"])
        self.assertEqual(1, result["summary"]["critical_projects"])
        self.assertEqual(1, result["summary"]["attention_projects"])
        self.assertEqual(3, result["summary"]["blocked_tasks"])

        with patch.object(
            project_health_service.server_client, "get_project_health_portfolio", return_value=None,
        ):
            offline = project_health_service.resolve_project_health_portfolio(LOCAL_USER_ID)
        server_row = next(row for row in offline["items"] if row["project"]["id"] == "server-project")
        self.assertTrue(server_row["health"]["stale"])
        self.assertEqual("server-cache", server_row["health"]["source"])
        self.assertNotIn("not-accessible", [row["project"]["id"] for row in offline["items"]])


if __name__ == "__main__":
    unittest.main()
