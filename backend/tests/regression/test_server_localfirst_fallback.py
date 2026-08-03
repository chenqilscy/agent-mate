"""WB-063 local-first 回退不变量 (SV-01/02/03/05).

验证 Server 重构的 local-first 回退契约，全部确定性、不依赖真实 Server、不需 LLM：
  SV-01 纯本地零变化：AGENTMATE_SERVER_URL 空 → 所有同步函数返回空结果且不上云。
  SV-02 回退：URL 指向不可达地址时，pull/flush 一律返回空结果并不抛异常。
  SV-03 上行范围：仅 server 起源项目的时间线才入 outbox；local 项目与「上传默认关」均不上云。
  SV-05 密钥不上云：入队 payload 只含元数据(kind/title/summary/ext_id)，绝不含正文/凭据。

运行：cd backend && python -m pytest tests/regression/test_server_localfirst_fallback.py -q
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

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
import server_sync  # noqa: E402
import server_client  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class LocalFirstFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = getattr(settings, "AGENTMATE_SERVER_URL", "")
        self.old_upload = settings.AGENTMATE_SERVER_TIMELINE_UPLOAD
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"  # server_enabled=True
        settings.AGENTMATE_SERVER_TIMELINE_UPLOAD = True
        db.init_db()
        set_current_user_id(LOCAL_USER_ID)

    def tearDown(self) -> None:
        set_current_user_id(None)
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url
        settings.AGENTMATE_SERVER_TIMELINE_UPLOAD = self.old_upload
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    # ---- SV-01 纯本地零变化 -------------------------------------------- #
    def test_pure_local_zero_change(self) -> None:
        old = settings.AGENTMATE_SERVER_URL
        settings.AGENTMATE_SERVER_URL = ""
        try:
            self.assertFalse(settings.server_enabled)
            self.assertEqual({"pushed": 0, "pending": 0}, server_sync.flush_outbox())
            self.assertEqual({"downlinked": 0, "reachable": False}, server_sync.pull_catalog("tok"))
            sess = SimpleNamespace(project_id="p", title="t", id="s")
            self.assertFalse(server_sync.enqueue_timeline_event(session=sess, actor_id=LOCAL_USER_ID))
        finally:
            settings.AGENTMATE_SERVER_URL = old

    # ---- SV-02 不可达回退（不抛异常）---------------------------------- #
    def test_unreachable_server_falls_back_gracefully(self) -> None:
        with patch.object(server_client, "list_projects", return_value=None), \
             patch.object(server_client, "pull_catalog_snapshot", return_value=None), \
             patch.object(server_client, "list_all_catalog", return_value=None):
            res = server_sync.pull("tok")
            self.assertEqual({"synced": 0, "projects": []}, res)
            cat = server_sync.pull_catalog("tok")
            self.assertEqual({"downlinked": 0, "reachable": False}, cat)
            out = server_sync.flush_outbox()
            self.assertEqual({"pushed": 0, "pending": 0}, out)

    # ---- SV-03 上行范围：仅 server 项目 + 上传开 ----------------------- #
    def test_timeline_upload_scoped_to_server_projects(self) -> None:
        local_p = db.create_project(owner_id=LOCAL_USER_ID, name="local-only")
        sess_local = SimpleNamespace(project_id=local_p.id, title="L", id="s-l")
        self.assertFalse(server_sync.enqueue_timeline_event(session=sess_local, actor_id=LOCAL_USER_ID))
        self.assertEqual(0, len(db.list_pending_outbox()))

        db.mirror_server_project(id="svr-1", name="team", owner_id=LOCAL_USER_ID)
        sess_svr = SimpleNamespace(project_id="svr-1", title="完成联调", id="s-s")
        self.assertTrue(server_sync.enqueue_timeline_event(session=sess_svr, actor_id=LOCAL_USER_ID))
        self.assertEqual(1, len(db.list_pending_outbox()))

    # ---- SV-05 密钥不上云：payload 仅元数据 --------------------------- #
    def test_enqueued_payload_is_metadata_only(self) -> None:
        db.mirror_server_project(id="svr-2", name="team2", owner_id=LOCAL_USER_ID)
        sess = SimpleNamespace(project_id="svr-2", title="真实会话标题", id="s-2")
        server_sync.enqueue_timeline_event(session=sess, actor_id=LOCAL_USER_ID)
        payload = db.list_pending_outbox()[0]["payload"]
        self.assertEqual({"kind", "title", "summary", "ext_id"}, set(payload.keys()))
        self.assertEqual("真实会话标题", payload["title"])
        self.assertEqual("", payload["summary"])
        self.assertNotIn("messages", payload)
        self.assertNotIn("content", payload)
        self.assertNotIn("LLM", repr(payload))
        self.assertNotIn("API_KEY", repr(payload))

    # ---- 默认关上传（隐私铁律）---------------------------------------- #
    def test_upload_disabled_by_default_does_not_queue(self) -> None:
        old = settings.AGENTMATE_SERVER_TIMELINE_UPLOAD
        settings.AGENTMATE_SERVER_TIMELINE_UPLOAD = False
        try:
            db.mirror_server_project(id="svr-3", name="team3", owner_id=LOCAL_USER_ID)
            sess = SimpleNamespace(project_id="svr-3", title="x", id="s-3")
            self.assertFalse(server_sync.enqueue_timeline_event(session=sess, actor_id=LOCAL_USER_ID))
            self.assertEqual(0, len(db.list_pending_outbox()))
        finally:
            settings.AGENTMATE_SERVER_TIMELINE_UPLOAD = old


if __name__ == "__main__":
    unittest.main()
