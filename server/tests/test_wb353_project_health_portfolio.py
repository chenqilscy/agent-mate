"""WB-353 access-scoped Server portfolio health coverage."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.project_health import project_health_portfolio  # noqa: E402


class ProjectHealthPortfolioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner-353", password="password123")
        self.member = db.create_account(name="member-353", password="password123")
        self.outsider = db.create_account(name="outsider-353", password="password123")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_portfolio_is_access_scoped_sorted_and_excludes_archived(self) -> None:
        attention = db.create_project(name="attention", owner_id=self.owner.id)
        critical = db.create_project(name="critical", owner_id=self.owner.id)
        archived = db.create_project(name="archived", owner_id=self.owner.id)
        db.add_project_member(critical.id, self.member.id, Role.MEMBER)
        db.create_work_item(project_id=attention.id, title="blocked", status="paused")
        db.create_project_governance(
            project_id=critical.id, record_type="risk", title="capacity", description="",
            status="open", severity="critical", owner_id="", response="", rationale="",
            work_item_id="", milestone_id="", run_id="", artifact_id="",
            evidence_label="", created_by=self.owner.id,
        )
        db.update_project(archived.id, archived_at=time.time())

        owner_view = project_health_portfolio(self.owner)
        self.assertEqual([critical.id, attention.id], [row["project"]["id"] for row in owner_view["items"]])
        self.assertEqual(2, owner_view["summary"]["total_projects"])
        self.assertEqual(1, owner_view["summary"]["critical_projects"])
        self.assertEqual(1, owner_view["summary"]["attention_projects"])
        self.assertFalse(owner_view["stale"])

        member_view = project_health_portfolio(self.member)
        self.assertEqual([critical.id], [row["project"]["id"] for row in member_view["items"]])
        self.assertEqual(Role.MEMBER.value, member_view["items"][0]["project"]["role"])
        self.assertEqual([], project_health_portfolio(self.outsider)["items"])


if __name__ == "__main__":
    unittest.main()
