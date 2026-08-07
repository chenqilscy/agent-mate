"""WB-293..295 project governance, PM persistence and strict validation."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from models import Role  # noqa: E402
from routers.comments import CommentBody, post_comment  # noqa: E402
from routers.pm import PmPreferencesBody, PmTemplate, PmView, get_pm_preferences, update_pm_preferences  # noqa: E402
from routers.projects import UpdateProjectBody, archive_project, restore_project, transfer_project, TransferProjectBody, update_project  # noqa: E402
from routers.work_items import CreateBody, create_item  # noqa: E402


class ProjectManagementIntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.admin = db.create_account(name="admin", password="password123")
        self.member = db.create_account(name="member", password="password123")
        self.viewer = db.create_account(name="viewer", password="password123")
        self.project = db.create_project(name="Delivery", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.admin.id, Role.ADMIN)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None: conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_configuration_and_comments_honor_role_and_archive_boundaries(self) -> None:
        with self.assertRaisesRegex(HTTPException, "requires Admin/Owner"):
            update_project(self.project.id, UpdateProjectBody(name="member edit"), self.member)
        updated = update_project(self.project.id, UpdateProjectBody(name="Admin edit"), self.admin)
        self.assertEqual("Admin edit", updated["name"])
        with self.assertRaisesRegex(HTTPException, "Viewer is read-only"):
            post_comment(self.project.id, CommentBody(body="not allowed"), self.viewer)
        archive_project(self.project.id, self.owner)
        with self.assertRaisesRegex(HTTPException, "archived project is read-only"):
            create_item(self.project.id, CreateBody(title="blocked"), self.member)
        restored = restore_project(self.project.id, self.owner)
        self.assertEqual(0, restored["archived_at"])

    def test_owner_transfer_is_limited_to_existing_writable_member(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Member or Admin"):
            transfer_project(self.project.id, TransferProjectBody(account_id=self.viewer.id), self.owner)
        result = transfer_project(self.project.id, TransferProjectBody(account_id=self.member.id), self.owner)
        self.assertEqual(self.member.id, result["owner_id"])
        self.assertEqual(Role.ADMIN, db.project_access_role(self.project.id, self.owner.id))

    def test_pm_preferences_are_project_shared_and_account_private(self) -> None:
        template = PmTemplate(id="tpl-1", name="Bug", values={"priority": "high"})
        view = PmView(id="view-1", name="Mine", filters={"search": "api"})
        update_pm_preferences(self.project.id, PmPreferencesBody(templates=[template], views=[view]), self.member)
        owner_values = get_pm_preferences(self.project.id, self.owner)
        member_values = get_pm_preferences(self.project.id, self.member)
        self.assertEqual("Bug", owner_values["templates"][0]["name"])
        self.assertEqual([], owner_values["views"])
        self.assertEqual("Mine", member_values["views"][0]["name"])
        with self.assertRaisesRegex(HTTPException, "Viewer is read-only"):
            update_pm_preferences(
                self.project.id,
                PmPreferencesBody(templates=[PmTemplate(id="viewer", name="Blocked", values={})]),
                self.viewer,
            )
        with self.assertRaisesRegex(HTTPException, "requires Admin/Owner"):
            update_pm_preferences(self.project.id, PmPreferencesBody(wip={"doing": 2}), self.member)
        update_pm_preferences(self.project.id, PmPreferencesBody(wip={"doing": 2}), self.admin)
        self.assertEqual(2, get_pm_preferences(self.project.id, self.owner)["wip"]["doing"])

    def test_pm_preference_revisions_reject_stale_cross_surface_snapshots_atomically(self) -> None:
        initial = get_pm_preferences(self.project.id, self.member)
        first = update_pm_preferences(
            self.project.id,
            PmPreferencesBody(
                templates=[PmTemplate(id="tpl-app", name="App", values={"status": "review"})],
                views=[PmView(id="view-app", name="App view", filters={"group": "assignee"})],
                expected_shared_updated_at=initial["shared_updated_at"],
                expected_views_updated_at=initial["views_updated_at"],
            ),
            self.member,
        )
        update_pm_preferences(
            self.project.id,
            PmPreferencesBody(
                wip={"doing": 3},
                expected_shared_updated_at=first["shared_updated_at"],
            ),
            self.admin,
        )

        with self.assertRaises(HTTPException) as stale:
            update_pm_preferences(
                self.project.id,
                PmPreferencesBody(
                    templates=[PmTemplate(id="tpl-stale", name="Stale", values={})],
                    views=[PmView(id="view-stale", name="Stale view", filters={})],
                    expected_shared_updated_at=first["shared_updated_at"],
                    expected_views_updated_at=first["views_updated_at"],
                ),
                self.member,
            )
        self.assertEqual(409, stale.exception.status_code)
        current = get_pm_preferences(self.project.id, self.member)
        self.assertEqual(["tpl-app"], [item["id"] for item in current["templates"]])
        self.assertEqual(["view-app"], [item["id"] for item in current["views"]])
        self.assertEqual(3, current["wip"]["doing"])

    def test_task_values_are_rejected_instead_of_silently_rewritten(self) -> None:
        with self.assertRaisesRegex(HTTPException, "assignee must"):
            create_item(self.project.id, CreateBody(title="Bad owner", assignee="outsider"), self.owner)
        with self.assertRaisesRegex(HTTPException, "due_date"):
            create_item(self.project.id, CreateBody(title="Bad dates", start_date="2026-07-24", due_date="2026-07-23"), self.owner)
        with self.assertRaisesRegex(HTTPException, "estimate_h"):
            create_item(self.project.id, CreateBody(title="Bad hours", estimate_h=-1), self.owner)


if __name__ == "__main__":
    unittest.main()
