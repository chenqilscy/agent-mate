"""M7 协作权限矩阵 (C2/C4).

验证项目成员·角色门禁：Owner/Admin 可管理、Member/Viewer 仅可读、陌生人无访问权；
以及邀请成员会向消息中心写入真实通知事件 (M7 C4)。全部确定性，不需 Server/LLM。

运行：cd backend && python -m pytest tests/regression/test_collaboration_role_matrix.py -q
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException  # noqa: E402
from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import projects as projects_router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID, Role  # noqa: E402


class CollaborationRoleMatrixTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = getattr(settings, "AGENTMATE_SERVER_URL", "")
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = ""  # 纯本地权威
        db.init_db()
        self.owner = "owner-uid"
        self.admin = "admin-uid"
        self.member = "member-uid"
        self.viewer = "viewer-uid"
        self.stranger = "stranger-uid"
        self.proj = db.create_project(owner_id=self.owner, name="proj")
        db.add_project_member(self.proj.id, self.admin, Role.ADMIN)
        db.add_project_member(self.proj.id, self.member, Role.MEMBER)
        db.add_project_member(self.proj.id, self.viewer, Role.VIEWER)

    def tearDown(self) -> None:
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

    # ---- 角色解析矩阵 --------------------------------------------------- #
    def test_project_access_role_matrix(self) -> None:
        self.assertEqual(Role.OWNER, db.project_access_role(self.proj.id, self.owner))
        self.assertEqual(Role.ADMIN, db.project_access_role(self.proj.id, self.admin))
        self.assertEqual(Role.MEMBER, db.project_access_role(self.proj.id, self.member))
        self.assertEqual(Role.VIEWER, db.project_access_role(self.proj.id, self.viewer))
        self.assertIsNone(db.project_access_role(self.proj.id, self.stranger))

    # ---- 访问门禁：owner + 所有成员可读 -------------------------------- #
    def test_require_access_allows_owner_and_all_members(self) -> None:
        for uid in (self.owner, self.admin, self.member, self.viewer):
            self.assertIsNotNone(projects_router._require_access(self.proj.id, uid))

    def test_require_access_rejects_stranger(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            projects_router._require_access(self.proj.id, self.stranger)
        self.assertEqual(404, ctx.exception.status_code)

    # ---- 管理门禁：仅 Owner/Admin -------------------------------------- #
    def test_require_manage_allows_owner_and_admin(self) -> None:
        self.assertEqual(Role.OWNER, projects_router._require_manage(self.proj.id, self.owner))
        self.assertEqual(Role.ADMIN, projects_router._require_manage(self.proj.id, self.admin))

    def test_require_manage_rejects_member_and_viewer(self) -> None:
        for uid in (self.member, self.viewer):
            with self.assertRaises(HTTPException) as ctx:
                projects_router._require_manage(self.proj.id, uid)
            self.assertEqual(403, ctx.exception.status_code)

    # ---- M7 C4：邀请 → 消息中心真事件 -------------------------------- #
    def test_invite_creates_message_center_notification(self) -> None:
        with patch.object(projects_router, "current_user",
                          return_value=SimpleNamespace(id=self.owner, name="Owner")), \
             patch.object(projects_router.db, "get_user_by_name",
                          return_value=(SimpleNamespace(id=self.member), None)):
            projects_router.add_member(
                self.proj.id,
                projects_router.AddMemberBody(name="mate", role="Member"),
                authorization="",
            )
        notes = db.list_notifications(self.member)
        self.assertTrue(any(n["kind"] == "member_added" for n in notes))
        self.assertTrue(any(n["project_id"] == self.proj.id for n in notes))


if __name__ == "__main__":
    unittest.main()
