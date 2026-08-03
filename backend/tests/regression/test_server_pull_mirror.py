"""WB-062 Phase 2 下行 pull 镜像 (SV-04).

验证本地⇄Server 同步的「下行」分支：用 Server token 拉取项目 + 成员，幂等镜像进本地 DB。
全部确定性、用 mock server_client、不依赖真实 Server、不需 LLM：
  - 可达时：projects 镜像为 origin='server'，成员按 account_id+updated_at 增量合并。
  - 幂等：重复 pull 相同数据不会重复插入成员。
  - 回退：成员子请求不可达(None)时，保留上次镜像（不清空本地权限镜像，last-known-good）。

运行：cd backend && python -m pytest tests/regression/test_server_pull_mirror.py -q
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
import server_sync  # noqa: E402
import server_client  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


def _proj(pid: str, owner: str) -> dict:
    return {
        "id": pid,
        "name": f"Server Project {pid}",
        "owner_id": owner,
        "instruction": "",
        "connectors": [],
        "experts": [],
        "skills": [],
        "knowledge_ids": [],
        "created_at": 1.0,
        "updated_at": 1.0,
    }


def _members(pid: str, owner: str) -> list[dict]:
    return [
        {"account_id": owner, "name": "Owner", "is_owner": True, "role": "Owner", "updated_at": 1.0},
        {"account_id": f"{pid}-mate", "name": "Mate", "role": "Member", "updated_at": 1.0},
    ]


class PullMirrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = getattr(settings, "AGENTMATE_SERVER_URL", "")
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"  # server_enabled=True
        db.init_db()
        set_current_user_id(LOCAL_USER_ID)
        db.cache_token("tok", LOCAL_USER_ID)  # pull 用 user_id_for_token 做 reconcile

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

    # ---- 可达：镜像项目 + 成员 --------------------------------------- #
    def test_pull_mirrors_projects_and_members(self) -> None:
        projects = [_proj("p1", "owner-1"), _proj("p2", "owner-2")]
        members = {"p1": _members("p1", "owner-1"), "p2": _members("p2", "owner-2")}
        with patch.object(server_client, "list_projects", return_value=projects), \
             patch.object(server_client, "list_project_members",
                          side_effect=lambda tok, pid: members[pid]):
            res = server_sync.pull("tok")

        self.assertEqual(2, res["synced"])
        self.assertEqual(2, len(res["projects"]))
        self.assertEqual("server", db.get_project("p1").origin)
        self.assertEqual("server", db.get_project("p2").origin)

        mem1 = db.list_project_members("p1")
        # owner 由 projects.owner_id 合成排第一，+ 1 个非 owner 成员
        self.assertEqual(2, len(mem1))
        self.assertTrue(any(m["user_id"] == "p1-mate" for m in mem1))

    # ---- 幂等：重复 pull 不重复插入成员 ----------------------------- #
    def test_pull_is_idempotent(self) -> None:
        projects = [_proj("p1", "owner-1")]
        members = {"p1": _members("p1", "owner-1")}
        with patch.object(server_client, "list_projects", return_value=projects), \
             patch.object(server_client, "list_project_members",
                          side_effect=lambda tok, pid: members[pid]):
            server_sync.pull("tok")
            before = len(db.list_project_members("p1"))
            server_sync.pull("tok")
            after = len(db.list_project_members("p1"))
        self.assertEqual(before, after)

    # ---- 回退：成员子请求不可达时保留镜像 --------------------------- #
    def test_pull_preserves_members_when_subrequest_unreachable(self) -> None:
        projects = [_proj("p1", "owner-1")]
        members = {"p1": _members("p1", "owner-1")}
        calls = {"n": 0}

        def fake_members(token, pid):
            calls["n"] += 1
            # 第一次 pull 正常返回；第二次（成员子请求不可达）返回 None
            return members[pid] if calls["n"] <= 1 else None

        with patch.object(server_client, "list_projects", return_value=projects), \
             patch.object(server_client, "list_project_members", side_effect=fake_members):
            server_sync.pull("tok")
            before = len(db.list_project_members("p1"))
            server_sync.pull("tok")
            after = len(db.list_project_members("p1"))
        self.assertEqual(before, after)  # 不清空本地权限镜像（last-known-good）


if __name__ == "__main__":
    unittest.main()
