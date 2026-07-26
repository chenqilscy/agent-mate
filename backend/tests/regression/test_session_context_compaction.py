"""WB-325 persistent Session summary and bounded recent-history context."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import session_context  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class SessionContextCompactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_budget = settings.SESSION_HISTORY_TOKEN_BUDGET
        self.old_recent = settings.SESSION_RECENT_TOKEN_BUDGET
        self.old_source = settings.SESSION_SUMMARY_SOURCE_TOKEN_BUDGET
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.SESSION_HISTORY_TOKEN_BUDGET = 60
        settings.SESSION_RECENT_TOKEN_BUDGET = 30
        settings.SESSION_SUMMARY_SOURCE_TOKEN_BUDGET = 200
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="长会话")

    def tearDown(self) -> None:
        self._close_connection()
        settings.DB_PATH = self.old_db
        settings.SESSION_HISTORY_TOKEN_BUDGET = self.old_budget
        settings.SESSION_RECENT_TOKEN_BUDGET = self.old_recent
        settings.SESSION_SUMMARY_SOURCE_TOKEN_BUDGET = self.old_source
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _add(self, role: str, content: str) -> None:
        db.add_message(
            session_id=self.session.id,
            role=role,
            content=content,
            actor=LOCAL_USER_ID if role == "user" else "assistant",
        )

    def _build(self, session=None):
        return asyncio.run(session_context.build_llm_messages(
            session or db.get_session(self.session.id),
            db.list_messages(self.session.id),
            new_user_text="当前问题",
            system_prompt="系统规则",
            model="test-model",
            api_base="http://llm.invalid",
            api_key="test",
            chat_path="/chat/completions",
        ))

    def test_schema_migration_and_summary_cas(self) -> None:
        columns = {row["name"] for row in db.get_conn().execute("PRAGMA table_info(sessions)")}
        self.assertTrue({"summary", "summary_cursor", "summary_updated_at"}.issubset(columns))
        self.assertTrue(db.update_session_summary(
            self.session.id, expected_cursor=0, summary="第一版", summary_cursor=2,
        ))
        self.assertFalse(db.update_session_summary(
            self.session.id, expected_cursor=0, summary="并发旧版", summary_cursor=1,
        ))
        latest = db.get_session(self.session.id)
        self.assertEqual("第一版", latest.summary)
        self.assertEqual(2, latest.summary_cursor)

    def test_small_session_keeps_full_history_without_summary_call(self) -> None:
        settings.SESSION_HISTORY_TOKEN_BUDGET = 500
        self._add("user", "你好")
        self._add("assistant", "你好，有什么可以帮你？")
        with patch.object(
            session_context, "_generate_summary", new=AsyncMock(return_value="不应调用"),
        ) as summarize:
            messages = self._build()
        summarize.assert_not_awaited()
        self.assertEqual(
            ["system", "user", "assistant", "user"],
            [message["role"] for message in messages],
        )
        self.assertEqual("你好", messages[1]["content"])

    def test_over_budget_compacts_old_turns_and_persists_cursor(self) -> None:
        for role, text in (
            ("user", "旧问题甲" * 12),
            ("assistant", "旧回答甲" * 12),
            ("user", "旧问题乙" * 12),
            ("assistant", "旧回答乙" * 12),
            ("user", "最近问题"),
            ("assistant", "最近回答"),
        ):
            self._add(role, text)

        with patch.object(
            session_context, "_generate_summary",
            new=AsyncMock(return_value="## 已确认事实与决定\n- 已处理两个旧问题"),
        ) as summarize:
            messages = self._build()
        summarize.assert_awaited_once()
        latest = db.get_session(self.session.id)
        self.assertEqual(4, latest.summary_cursor)
        self.assertIn("已处理两个旧问题", latest.summary)
        rendered = "\n".join(message["content"] for message in messages)
        self.assertNotIn("旧问题甲", rendered)
        self.assertNotIn("旧问题乙", rendered)
        self.assertIn("最近问题", rendered)
        self.assertIn("当前问题", rendered)

        with patch.object(
            session_context, "_generate_summary", new=AsyncMock(return_value="不应再次压缩"),
        ) as summarize_again:
            second = self._build(latest)
        summarize_again.assert_not_awaited()
        self.assertIn("已处理两个旧问题", "\n".join(item["content"] for item in second))

    def test_summary_failure_falls_back_to_bounded_recent_turn(self) -> None:
        for role, text in (
            ("user", "很早的问题" * 15),
            ("assistant", "很早的回答" * 15),
            ("user", "保留的最近问题"),
            ("assistant", "保留的最近回答"),
        ):
            self._add(role, text)
        with patch.object(
            session_context, "_generate_summary",
            new=AsyncMock(side_effect=RuntimeError("summary unavailable")),
        ):
            messages = self._build()
        self.assertEqual(0, db.get_session(self.session.id).summary_cursor)
        rendered = "\n".join(message["content"] for message in messages)
        self.assertNotIn("很早的问题", rendered)
        self.assertIn("保留的最近问题", rendered)
        self.assertIn("当前问题", rendered)

    def test_single_huge_recent_turn_is_explicitly_clipped(self) -> None:
        self._add("user", "超长输入" * 200)
        self._add("assistant", "超长输出" * 200)
        with patch.object(
            session_context, "_generate_summary",
            new=AsyncMock(return_value="不应调用"),
        ):
            messages = self._build()
        history = messages[1:-1]
        self.assertLessEqual(
            sum(session_context.approx_tokens(item["content"]) + 4 for item in history),
            settings.SESSION_RECENT_TOKEN_BUDGET + 2,
        )
        self.assertIn("截断", "\n".join(item["content"] for item in history))


if __name__ == "__main__":
    unittest.main()
