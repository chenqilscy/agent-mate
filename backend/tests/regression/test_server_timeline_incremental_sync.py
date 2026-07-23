"""WB-112d/e: Server timeline readback and conflict-visible incremental mirrors."""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
import server_sync  # noqa: E402
from routers import server as server_router  # noqa: E402
from routers import projects as projects_router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class ServerTimelineIncrementalSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = settings.AGENTMATE_SERVER_URL
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        db.init_db()
        set_current_user_id(LOCAL_USER_ID)
        db.mirror_server_project(
            id="project-1", name="共享项目", owner_id=LOCAL_USER_ID,
            instruction="remote-v1", created_at=10, updated_at=100,
        )
        db.cache_token("token", LOCAL_USER_ID)

    def tearDown(self) -> None:
        set_current_user_id(None)
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def test_timeline_reads_server_then_falls_back_to_scoped_cache(self) -> None:
        events = [{
            "id": "event-1", "project_id": "project-1", "actor_id": "mate-1",
            "actor_name": "队友", "kind": "session", "title": "完成接口联调",
            "summary": "", "ext_id": "session-remote", "created_at": 123,
        }]
        with patch.object(server_router.server_client, "list_timeline", return_value=events):
            online = server_router.server_timeline("project-1", authorization="Bearer token")
        self.assertTrue(online["reachable"])
        self.assertFalse(online["stale"])
        self.assertEqual("队友", online["events"][0]["actor_name"])

        with patch.object(server_router.server_client, "list_timeline", return_value=None):
            offline = server_router.server_timeline("project-1", authorization="Bearer token")
        self.assertFalse(offline["reachable"])
        self.assertTrue(offline["stale"])
        self.assertEqual("event-1", offline["events"][0]["id"])

        with self.assertRaises(HTTPException) as invalid:
            server_router.server_timeline("project-1", authorization="Bearer invalid-token")
        self.assertEqual(401, invalid.exception.status_code)

        stranger = db.create_user(name="stranger", password="pw")
        set_current_user_id(stranger.id)
        with self.assertRaises(HTTPException) as error:
            server_router.server_timeline("project-1", authorization="Bearer token")
        self.assertEqual(404, error.exception.status_code)

    def test_project_conflict_preserves_offline_edit_until_values_converge(self) -> None:
        db.update_project("project-1", instruction="local-offline")
        db.mirror_server_project(
            id="project-1", name="共享项目", owner_id=LOCAL_USER_ID,
            instruction="remote-v2", created_at=10, updated_at=200,
        )
        self.assertEqual("local-offline", db.get_project("project-1").instruction)
        conflicts = db.list_server_sync_conflicts("project-1")
        self.assertEqual(1, len(conflicts))
        self.assertEqual("concurrent_update", conflicts[0]["reason"])

        db.update_project("project-1", instruction="remote-v2")
        db.mirror_server_project(
            id="project-1", name="共享项目", owner_id=LOCAL_USER_ID,
            instruction="remote-v2", created_at=10, updated_at=200,
        )
        self.assertEqual(0, db.count_server_sync_conflicts("project-1"))

    def test_server_project_writes_fail_closed_while_local_projects_stay_writable(self) -> None:
        with patch.object(projects_router.server_client, "update_project", return_value=None):
            with self.assertRaises(HTTPException) as update_error:
                projects_router.update_project(
                    "project-1", projects_router.UpdateProjectBody(instruction="local-offline"),
                    authorization="Bearer token",
                )
        self.assertEqual(503, update_error.exception.status_code)
        self.assertEqual("remote-v1", db.get_project("project-1").instruction)
        self.assertEqual(0, db.count_server_sync_conflicts("project-1"))

        teammate = db.create_user(name="teammate", password="pw")
        with patch.object(projects_router.server_client, "add_member", return_value=None):
            with self.assertRaises(HTTPException) as add_error:
                projects_router.add_member(
                    "project-1", projects_router.AddMemberBody(name="teammate", role="Member"),
                    authorization="Bearer token",
                )
        self.assertEqual(503, add_error.exception.status_code)
        self.assertIsNone(db.project_member_role("project-1", teammate.id))

        db.add_project_member("project-1", teammate.id, Role.MEMBER)
        with patch.object(projects_router.server_client, "update_member", return_value=None):
            with self.assertRaises(HTTPException) as role_error:
                projects_router.update_member(
                    "project-1", teammate.id, projects_router.UpdateMemberBody(role="Admin"),
                    authorization="Bearer token",
                )
        self.assertEqual(503, role_error.exception.status_code)
        self.assertEqual(Role.MEMBER, db.project_member_role("project-1", teammate.id))

        with patch.object(projects_router.server_client, "remove_member", return_value=False):
            with self.assertRaises(HTTPException) as remove_error:
                projects_router.remove_member(
                    "project-1", teammate.id, authorization="Bearer token",
                )
        self.assertEqual(503, remove_error.exception.status_code)
        self.assertEqual(Role.MEMBER, db.project_member_role("project-1", teammate.id))

        local = db.create_project(owner_id=LOCAL_USER_ID, name="本机项目")
        with patch.object(projects_router.server_client, "update_project") as remote_update:
            updated = projects_router.update_project(
                local.id, projects_router.UpdateProjectBody(instruction="local-ok"),
                authorization="Bearer token",
            )
        remote_update.assert_not_called()
        self.assertEqual("local-ok", updated["instruction"])

    def test_work_items_and_milestones_merge_by_id_without_table_replacement(self) -> None:
        first = {
            "id": "work-1", "title": "远端初版", "status": "todo", "source": "手动",
            "assignee": "", "description": "", "labels": [], "created_at": 50, "updated_at": 100,
        }
        removable = {**first, "id": "work-clean", "title": "稍后远端删除"}
        db.mirror_server_work_items("project-1", [first, removable])
        db.update_work_item("work-1", title="本地离线标题")
        db.mirror_server_work_items("project-1", [{**first, "title": "远端并发标题", "updated_at": 200}])
        self.assertEqual("本地离线标题", db.get_work_item("work-1").title)
        self.assertIsNone(db.get_work_item("work-clean"))
        self.assertEqual("concurrent_update", db.list_server_sync_conflicts("project-1")[0]["reason"])

        milestone = {
            "id": "mile-1", "name": "一期", "description": "", "status": "open",
            "sort": 1, "created_at": 50, "updated_at": 100,
        }
        db.mirror_server_milestones("project-1", [milestone])
        db.update_milestone("mile-1", name="本地一期")
        db.mirror_server_milestones("project-1", [{**milestone, "name": "远端一期", "updated_at": 200}])
        self.assertEqual("本地一期", db.get_milestone("mile-1")["name"])
        reasons = {item["entity_type"]: item["reason"] for item in db.list_server_sync_conflicts("project-1")}
        self.assertEqual("concurrent_update", reasons["milestone"])

    def test_member_role_and_offline_delete_are_not_silently_overwritten(self) -> None:
        snapshot = [
            {"account_id": LOCAL_USER_ID, "name": "本地用户", "role": "Owner", "is_owner": True,
             "created_at": 10, "updated_at": 100},
            {"account_id": "member-1", "name": "队友", "role": "Member", "is_owner": False,
             "created_at": 20, "updated_at": 100},
        ]
        db.replace_server_project_members("project-1", snapshot)
        db.add_project_member("project-1", "member-1", Role.ADMIN)
        db.replace_server_project_members("project-1", [snapshot[0], {**snapshot[1], "role": "Viewer", "updated_at": 200}])
        # 权限字段 fail closed：Server Viewer 生效，本地 Admin 意图只留在冲突证据中。
        self.assertEqual(Role.VIEWER, db.project_member_role("project-1", "member-1"))
        self.assertEqual("permission_conflict", db.list_server_sync_conflicts("project-1")[0]["reason"])

        db.remove_project_member("project-1", "member-1")
        db.replace_server_project_members("project-1", [snapshot[0], {**snapshot[1], "updated_at": 300}])
        self.assertIsNone(db.project_member_role("project-1", "member-1"))
        self.assertEqual("local_deleted", db.list_server_sync_conflicts("project-1")[0]["reason"])

    def test_server_project_removal_revokes_cached_member_access(self) -> None:
        db.upsert_external_user("removed-member", "已移除成员")
        db.get_conn().execute(
            """INSERT INTO project_members
               (project_id,user_id,role,created_at,updated_at,server_updated_at,server_dirty)
               VALUES ('project-1','removed-member','Member',10,100,100,0)"""
        )
        db.get_conn().commit()
        self.assertEqual(Role.MEMBER, db.project_access_role("project-1", "removed-member"))
        db.reconcile_server_project_access("removed-member", set())
        self.assertIsNone(db.project_access_role("project-1", "removed-member"))

    def test_member_subrequest_failure_preserves_last_known_access(self) -> None:
        db.upsert_external_user("member-1", "队友")
        snapshot = [{
            "account_id": "member-1", "name": "队友", "role": "Member", "is_owner": False,
            "created_at": 20, "updated_at": 100,
        }]
        db.replace_server_project_members("project-1", snapshot)
        project = {
            "id": "project-1", "name": "共享项目", "owner_id": LOCAL_USER_ID,
            "instruction": "remote-v1", "created_at": 10, "updated_at": 100,
        }
        with (
            patch.object(server_sync.server_client, "list_projects", return_value=[project]),
            patch.object(server_sync.server_client, "list_project_members", return_value=None),
        ):
            result = server_sync.pull("uncached-token")
        self.assertEqual(1, result["synced"])
        self.assertEqual(Role.MEMBER, db.project_member_role("project-1", "member-1"))


if __name__ == "__main__":
    unittest.main()
