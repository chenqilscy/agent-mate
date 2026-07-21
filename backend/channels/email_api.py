"""邮件渠道底层客户端（WB-096）—— stdlib imaplib / smtplib / email。

IMAP 拉未读 + SMTP 回复。**阻塞**库（不像 Telegram 的 httpx 异步），由 manager 用
`asyncio.to_thread` 包着调，别在事件循环里直接 await 它。

永不抛异常给上层：出错回 (False, <可读文本>) 或空列表，让 poller 循环稳。凭据（账号/密码）
只在 config 里传入、只存后端 DB（gitignore），绝不进 git。
"""
from __future__ import annotations

import email
import hashlib
import imaplib
import socket
import smtplib
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from email.utils import parseaddr

_MAX_BODY = 20000   # 单封正文取用上限（字符）
_MAX_FETCH = 10     # 单轮最多处理几封


def _imap_conn(config: dict) -> imaplib.IMAP4_SSL:
    host = (config.get("imap_host") or "").strip()
    port = int(config.get("imap_port") or 993)
    conn = imaplib.IMAP4_SSL(host, port, timeout=30)  # 超时防坏 host 卡死线程
    conn.login((config.get("username") or "").strip(), config.get("password") or "")
    return conn


def _decode(s) -> str:
    if not s:
        return ""
    try:
        return str(make_header(decode_header(s)))
    except Exception:  # noqa: BLE001
        return str(s)


def _plain_body(msg) -> str:
    """取 text/plain 正文（优先），退回 text/html 粗转纯文本。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return _payload_text(part)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return _strip_html(_payload_text(part))
        return ""
    if msg.get_content_type() == "text/html":
        return _strip_html(_payload_text(msg))
    return _payload_text(msg)


def _payload_text(part) -> str:
    try:
        raw = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+\n", "\n", text).strip()


def _strip_quoted(body: str) -> str:
    """粗略去掉引用的历史回复，只留本次正文（常见分隔标记之前）。"""
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith(">"):
            break
        if s.startswith("On ") and s.endswith("wrote:"):
            break
        if s.startswith("在") and "写道" in s:
            break
        if set(s) == {"-"} and len(s) >= 10:  # 分隔线
            break
        lines.append(ln)
    out = "\n".join(lines).strip()
    return out or body.strip()


def verify(config: dict) -> tuple[bool, str]:
    """试登录 IMAP，校验账号/密码/host。"""
    try:
        conn = _imap_conn(config)
        conn.logout()
        return True, "邮箱连接正常。"
    except Exception as e:  # noqa: BLE001
        return False, f"IMAP 连接失败：{e}"


def _uid_validity(conn: imaplib.IMAP4_SSL) -> str:
    """Read the selected mailbox UIDVALIDITY; IMAP servers must expose it."""
    try:
        _name, data = conn.response("UIDVALIDITY")
        if data and data[0] is not None:
            raw = data[0]
            return raw.decode("ascii", errors="strict") if isinstance(raw, bytes) else str(raw)
    except Exception:  # noqa: BLE001
        pass
    return ""


def _message_key(raw: bytes, message_id: str, config: dict) -> str:
    # Message-ID is the cross-connection logical identity. Broken/missing IDs fall
    # back to the exact RFC message bytes, while UIDVALIDITY+UID remains only the
    # transport address used for STORE.
    normalized = "".join((message_id or "").split())
    mailbox = "|".join(str(config.get(k) or "").strip().lower() for k in ("imap_host", "imap_port", "username"))
    identity = ("message-id:" + normalized).encode("utf-8") if normalized else b"raw:" + raw
    basis = mailbox.encode("utf-8") + b"\0" + identity
    return hashlib.sha256(basis).hexdigest()


def _raw_fetch_payload(msg_data) -> bytes | None:
    for part in msg_data or []:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return part[1]
    return None


def fetch_unseen(config: dict) -> list[dict]:
    """PEEK unread mail without changing Seen; return stable logical + UID identity."""
    out: list[dict] = []
    try:
        conn = _imap_conn(config)
    except Exception:  # noqa: BLE001
        return out
    try:
        conn.select("INBOX")
        uid_validity = _uid_validity(conn)
        typ, data = conn.uid("SEARCH", None, "UNSEEN")
        if typ != "OK":
            return out
        ids = (data[0] or b"").split()
        for uid in ids[-_MAX_FETCH:]:
            typ, msg_data = conn.uid("FETCH", uid, "(UID BODY.PEEK[])")
            raw = _raw_fetch_payload(msg_data)
            if typ != "OK" or raw is None:
                continue
            msg = email.message_from_bytes(raw)
            # 跳过助手自己发出的回信（WB-098）：白名单含账号自己时，回信落回收件箱会被当新邮件
            # 反复处理 → 自我回复循环。发信打了 AgentMate 标记头，这里据此跳过。
            frm = parseaddr(msg.get("From", ""))[1].strip().lower()
            subject = _decode(msg.get("Subject", ""))
            body = _strip_quoted(_plain_body(msg))[:_MAX_BODY]
            message_id = "".join((msg.get("Message-ID", "") or "").split())
            out.append({
                "from": frm,
                "subject": subject,
                "body": body,
                "message_id": message_id,
                "message_key": _message_key(raw, message_id, config),
                "uid_validity": uid_validity,
                "imap_uid": uid.decode("ascii", errors="strict") if isinstance(uid, bytes) else str(uid),
                "ignore_reason": "assistant_reply" if msg.get("X-AgentMate-Assistant") else "",
            })
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


def _imap_search_value(value: str) -> str:
    value = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    if "\r" in value or "\n" in value:
        raise ValueError("invalid Message-ID")
    return f'"{value}"'


def mark_seen(config: dict, mail: dict) -> tuple[bool, str]:
    """Reconnect and mark exactly one message Seen using UID, never sequence number.

    UID is accepted only when UIDVALIDITY still matches. After a mailbox rebuild,
    Message-ID is searched and must resolve to exactly one UID; without that proof
    the function fails closed and the next PEEK poll can provide a fresh UID.
    """
    uid = str(mail.get("imap_uid") or "")
    expected_validity = str(mail.get("uid_validity") or "")
    message_id = str(mail.get("message_id") or "")
    if not uid:
        return False, "邮件缺少 IMAP UID，未标记已读。"
    try:
        conn = _imap_conn(config)
    except Exception as e:  # noqa: BLE001
        return False, f"IMAP 重连失败：{e}"
    try:
        typ, _data = conn.select("INBOX")
        if typ != "OK":
            return False, "IMAP INBOX 选择失败，未标记已读。"
        current_validity = _uid_validity(conn)
        target_uid = uid
        if not expected_validity or not current_validity or current_validity != expected_validity:
            if not message_id:
                return False, "UIDVALIDITY 已变化且邮件无 Message-ID，等待下轮 PEEK 取得新 UID。"
            typ, data = conn.uid("SEARCH", None, "HEADER", "Message-ID", _imap_search_value(message_id))
            matches = (data[0] or b"").split() if typ == "OK" and data else []
            if len(matches) != 1:
                return False, f"UIDVALIDITY 已变化，Message-ID 匹配 {len(matches)} 封，拒绝批量标记。"
            target_uid = matches[0].decode("ascii", errors="strict")
        typ, _data = conn.uid("STORE", target_uid, "+FLAGS.SILENT", r"(\Seen)")
        if typ != "OK":
            return False, f"IMAP UID STORE 失败（uid={target_uid}）。"
        return True, f"已标记邮件 uid={target_uid} 为 Seen。"
    except Exception as e:  # noqa: BLE001
        return False, f"IMAP 标记已读失败：{e}"
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def send_reply_delivery(
    config: dict,
    to: str,
    subject: str,
    body: str,
    in_reply_to: str = "",
    outbound_message_id: str = "",
) -> tuple[str, str]:
    """Send once and classify the SMTP result as sent/retryable/unknown.

    A disconnect while DATA is in flight is ambiguous: retrying can duplicate a
    reply, so callers must persist ``unknown`` and not automatically resend.
    """
    user = (config.get("username") or "").strip()
    host = (config.get("smtp_host") or "").strip()
    port = int(config.get("smtp_port") or 465)
    msg = MIMEText(body or "（空）", "plain", "utf-8")
    msg["From"] = user
    msg["To"] = to
    msg["X-AgentMate-Assistant"] = "1"  # 标记：收信时据此跳过助手自己的回信，防自我回复循环（WB-098）
    if outbound_message_id:
        msg["Message-ID"] = outbound_message_id
    subj = subject or ""
    msg["Subject"] = subj if subj.lower().startswith("re:") else f"Re: {subj}" if subj else "Re:"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    stage = "connect"
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        with server:
            stage = "authenticate"
            server.login(user, config.get("password") or "")
            stage = "send"
            refused = server.sendmail(user, [to], msg.as_string())
            if refused:
                return "retryable", f"SMTP 收件人被拒绝：{to}"
            stage = "accepted"
        return "sent", "已发送。"
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError) as e:
        return "retryable", f"SMTP 明确拒绝：{e}"
    except (smtplib.SMTPServerDisconnected, socket.timeout, TimeoutError, OSError) as e:
        if stage in {"send", "accepted"}:
            return "unknown", f"SMTP 发送结果未知（不自动重发）：{e}"
        return "retryable", f"SMTP 连接/鉴权失败：{e}"
    except Exception as e:  # noqa: BLE001
        if stage in {"send", "accepted"}:
            return "unknown", f"SMTP 发送结果未知（不自动重发）：{e}"
        return "retryable", f"SMTP 发送失败：{e}"


def send_reply(config: dict, to: str, subject: str, body: str, in_reply_to: str = "") -> tuple[bool, str]:
    """Backward-compatible bool wrapper used outside the durable email poller."""
    status, info = send_reply_delivery(config, to, subject, body, in_reply_to)
    return status == "sent", info
