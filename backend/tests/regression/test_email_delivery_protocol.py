"""WB-160 deterministic IMAP protocol and durable email-delivery coverage."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from channels import email_api, manager  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


def _message(index: int, *, message_id: str | None = None) -> bytes:
    mid = f"Message-ID: {message_id}\r\n" if message_id else ""
    return (
        f"From: sender@example.com\r\nSubject: mail {index}\r\n{mid}"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\nbody {index}\r\n"
    ).encode()


class FakeImap:
    def __init__(
        self,
        *,
        uid_validity: str = "100",
        messages: dict[str, bytes] | None = None,
        header_matches: list[str] | None = None,
        store_status: str = "OK",
    ) -> None:
        self.uid_validity = uid_validity
        self.messages = messages or {}
        self.header_matches = header_matches or []
        self.store_status = store_status
        self.calls: list[tuple] = []

    def select(self, mailbox: str):
        self.calls.append(("SELECT", mailbox))
        return "OK", [str(len(self.messages)).encode()]

    def response(self, name: str):
        self.calls.append(("RESPONSE", name))
        return name, [self.uid_validity.encode()]

    def uid(self, command: str, *args):
        self.calls.append((command, *args))
        if command == "SEARCH" and args[-1] == "UNSEEN":
            return "OK", [" ".join(self.messages).encode()]
        if command == "SEARCH":
            return "OK", [" ".join(self.header_matches).encode()]
        if command == "FETCH":
            uid = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
            raw = self.messages.get(uid)
            return ("OK", [(f"1 (UID {uid} BODY[] {{{len(raw or b'')}}})".encode(), raw)]) if raw else ("NO", [])
        if command == "STORE":
            return self.store_status, [b""]
        raise AssertionError((command, args))

    def logout(self):
        self.calls.append(("LOGOUT",))
        return "BYE", [b""]


class EmailImapProtocolTest(unittest.TestCase):
    def test_fetches_ten_messages_with_uid_body_peek_and_never_store(self) -> None:
        conn = FakeImap(messages={str(i): _message(i, message_id=f"<m{i}@example.com>") for i in range(1, 13)})
        with patch.object(email_api, "_imap_conn", return_value=conn):
            mails = email_api.fetch_unseen({})

        self.assertEqual(10, len(mails))
        self.assertEqual([str(i) for i in range(3, 13)], [mail["imap_uid"] for mail in mails])
        self.assertTrue(all(mail["uid_validity"] == "100" for mail in mails))
        fetches = [call for call in conn.calls if call[0] == "FETCH"]
        self.assertEqual(10, len(fetches))
        self.assertTrue(all(call[2] == "(UID BODY.PEEK[])" for call in fetches))
        self.assertFalse(any(call[0] == "STORE" for call in conn.calls))
        self.assertNotIn("RFC822", repr(conn.calls))

    def test_mark_seen_reconnects_and_uses_exact_uid_when_uidvalidity_matches(self) -> None:
        conn = FakeImap(uid_validity="100")
        mail = {"imap_uid": "42", "uid_validity": "100", "message_id": "<m42@example.com>"}
        with patch.object(email_api, "_imap_conn", return_value=conn):
            ok, _info = email_api.mark_seen({}, mail)

        self.assertTrue(ok)
        self.assertIn(("STORE", "42", "+FLAGS.SILENT", r"(\Seen)"), conn.calls)
        self.assertFalse(any(call[0] == "SEARCH" for call in conn.calls))

    def test_uidvalidity_change_falls_back_to_unique_message_id_uid(self) -> None:
        conn = FakeImap(uid_validity="200", header_matches=["84"])
        mail = {"imap_uid": "42", "uid_validity": "100", "message_id": "<m42@example.com>"}
        with patch.object(email_api, "_imap_conn", return_value=conn):
            ok, _info = email_api.mark_seen({}, mail)

        self.assertTrue(ok)
        self.assertIn(("SEARCH", None, "HEADER", "Message-ID", '"<m42@example.com>"'), conn.calls)
        self.assertIn(("STORE", "84", "+FLAGS.SILENT", r"(\Seen)"), conn.calls)

    def test_uidvalidity_change_fails_closed_for_ambiguous_message_id(self) -> None:
        conn = FakeImap(uid_validity="200", header_matches=["84", "85"])
        mail = {"imap_uid": "42", "uid_validity": "100", "message_id": "<duplicate@example.com>"}
        with patch.object(email_api, "_imap_conn", return_value=conn):
            ok, info = email_api.mark_seen({}, mail)

        self.assertFalse(ok)
        self.assertIn("匹配 2 封", info)
        self.assertFalse(any(call[0] == "STORE" for call in conn.calls))


class FakeSmtp:
    def __init__(self, send_error: Exception | None = None) -> None:
        self.send_error = send_error
        self.message = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def login(self, _user: str, _password: str) -> None:
        return None

    def sendmail(self, _from: str, _to: list[str], message: str):
        self.message = message
        if self.send_error:
            raise self.send_error
        return {}


class EmailSmtpProtocolTest(unittest.TestCase):
    def test_success_sends_stable_outbound_message_id(self) -> None:
        smtp = FakeSmtp()
        config = {"smtp_host": "smtp.example.com", "smtp_port": 465, "username": "agent@example.com", "password": "secret"}
        with patch.object(email_api.smtplib, "SMTP_SSL", return_value=smtp):
            status, _info = email_api.send_reply_delivery(
                config, "sender@example.com", "hello", "done",
                "<inbound@example.com>", "<agentmate-stable@example.com>",
            )

        self.assertEqual("sent", status)
        self.assertIn("Message-ID: <agentmate-stable@example.com>", smtp.message)
        self.assertIn("In-Reply-To: <inbound@example.com>", smtp.message)

    def test_disconnect_during_send_is_unknown_not_retryable(self) -> None:
        smtp = FakeSmtp(email_api.smtplib.SMTPServerDisconnected("lost after DATA"))
        config = {"smtp_host": "smtp.example.com", "smtp_port": 465, "username": "agent@example.com", "password": "secret"}
        with patch.object(email_api.smtplib, "SMTP_SSL", return_value=smtp):
            status, info = email_api.send_reply_delivery(
                config, "sender@example.com", "hello", "done", outbound_message_id="<stable@example.com>"
            )

        self.assertEqual("unknown", status)
        self.assertIn("不自动重发", info)


class EmailDeliveryManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self._close_db()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()
        assistant = db.create_assistant(owner_id=LOCAL_USER_ID, name="mail agent")
        self.channel = db.create_channel(
            assistant_id=assistant["id"],
            type="email",
            config={
                "imap_host": "imap.example.com", "smtp_host": "smtp.example.com",
                "username": "agent@example.com", "password": "secret",
                "allow_from": "sender@example.com",
            },
        )
        self.mail = {
            "from": "sender@example.com", "subject": "hello", "body": "work",
            "message_id": "<inbound@example.com>", "message_key": "stable-key",
            "uid_validity": "100", "imap_uid": "42", "ignore_reason": "",
        }

    def tearDown(self) -> None:
        manager._busy.clear()
        manager._session_locks.clear()
        self._close_db()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    @staticmethod
    def _close_db() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()

    async def test_seen_failure_retries_only_store_not_agent_or_smtp(self) -> None:
        run = AsyncMock(return_value=(True, "done"))
        with (
            patch.object(manager, "_run_agent_result", run),
            patch.object(email_api, "send_reply_delivery", return_value=("sent", "ok")) as send,
            patch.object(email_api, "mark_seen", side_effect=[(False, "offline"), (True, "ok")]) as mark,
        ):
            await manager._handle_email(self.channel["id"], self.mail)
            first = db.get_email_delivery(self.channel["id"], "stable-key")
            self.assertEqual("replied", first["status"])
            await manager._handle_email(self.channel["id"], self.mail)

        self.assertEqual(1, run.await_count)
        self.assertEqual(1, send.call_count)
        self.assertEqual(2, mark.call_count)
        self.assertEqual("seen", db.get_email_delivery(self.channel["id"], "stable-key")["status"])

    async def test_agent_failure_stays_unseen_and_retries_before_one_reply(self) -> None:
        run = AsyncMock(side_effect=[(False, "llm down"), (True, "recovered")])
        with (
            patch.object(manager, "_run_agent_result", run),
            patch.object(email_api, "send_reply_delivery", return_value=("sent", "ok")) as send,
            patch.object(email_api, "mark_seen", return_value=(True, "ok")) as mark,
        ):
            await manager._handle_email(self.channel["id"], self.mail)
            failed = db.get_email_delivery(self.channel["id"], "stable-key")
            self.assertEqual("retryable", failed["status"])
            self.assertEqual(0, send.call_count)
            self.assertEqual(0, mark.call_count)
            await manager._handle_email(self.channel["id"], self.mail)

        final = db.get_email_delivery(self.channel["id"], "stable-key")
        self.assertEqual("seen", final["status"])
        self.assertEqual(2, final["attempts"])
        self.assertEqual(1, send.call_count)
        self.assertEqual(1, mark.call_count)

    async def test_restart_during_smtp_is_quarantined_and_never_resent(self) -> None:
        db.observe_email_delivery(self.channel["id"], self.mail)
        db.claim_email_delivery(self.channel["id"], "stable-key")
        db.update_email_delivery(self.channel["id"], "stable-key", "reply_ready", reply="done")
        db.update_email_delivery(
            self.channel["id"], "stable-key", "sending", outbound_message_id="<stable@example.com>"
        )
        db.recover_email_deliveries(self.channel["id"])

        with (
            patch.object(manager, "_run_agent_result", AsyncMock()) as run,
            patch.object(email_api, "send_reply_delivery") as send,
            patch.object(email_api, "mark_seen", return_value=(True, "ok")) as mark,
        ):
            await manager._handle_email(self.channel["id"], self.mail)

        self.assertEqual(0, run.await_count)
        self.assertEqual(0, send.call_count)
        self.assertEqual(1, mark.call_count)
        self.assertEqual("delivery_unknown_seen", db.get_email_delivery(self.channel["id"], "stable-key")["status"])


if __name__ == "__main__":
    unittest.main()
