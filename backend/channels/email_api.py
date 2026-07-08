"""邮件渠道底层客户端（WB-096）—— stdlib imaplib / smtplib / email。

IMAP 拉未读 + SMTP 回复。**阻塞**库（不像 Telegram 的 httpx 异步），由 manager 用
`asyncio.to_thread` 包着调，别在事件循环里直接 await 它。

永不抛异常给上层：出错回 (False, <可读文本>) 或空列表，让 poller 循环稳。凭据（账号/密码）
只在 config 里传入、只存后端 DB（gitignore），绝不进 git。
"""
from __future__ import annotations

import email
import imaplib
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


def fetch_unseen(config: dict) -> list[dict]:
    """拉未读邮件并标记已读，返回 [{from, subject, body, message_id}]。永不抛异常。"""
    out: list[dict] = []
    try:
        conn = _imap_conn(config)
    except Exception:  # noqa: BLE001
        return out
    try:
        conn.select("INBOX")
        typ, data = conn.search(None, "UNSEEN")
        if typ != "OK":
            return out
        ids = (data[0] or b"").split()
        for num in ids[-_MAX_FETCH:]:
            typ, msg_data = conn.fetch(num, "(RFC822)")  # RFC822 会顺带标记 \Seen
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            # 跳过助手自己发出的回信（WB-098）：白名单含账号自己时，回信落回收件箱会被当新邮件
            # 反复处理 → 自我回复循环。发信打了 X-WorkBuddy-Assistant 头，这里据此跳过。
            if msg.get("X-WorkBuddy-Assistant"):
                continue
            frm = parseaddr(msg.get("From", ""))[1].strip().lower()
            subject = _decode(msg.get("Subject", ""))
            body = _strip_quoted(_plain_body(msg))[:_MAX_BODY]
            out.append({"from": frm, "subject": subject, "body": body, "message_id": msg.get("Message-ID", "")})
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


def send_reply(config: dict, to: str, subject: str, body: str, in_reply_to: str = "") -> tuple[bool, str]:
    """SMTP 发送回复。465→SSL，其它端口→STARTTLS。永不抛异常。"""
    user = (config.get("username") or "").strip()
    host = (config.get("smtp_host") or "").strip()
    port = int(config.get("smtp_port") or 465)
    msg = MIMEText(body or "（空）", "plain", "utf-8")
    msg["From"] = user
    msg["To"] = to
    msg["X-WorkBuddy-Assistant"] = "1"  # 标记：收信时据此跳过助手自己的回信，防自我回复循环（WB-098）
    subj = subject or ""
    msg["Subject"] = subj if subj.lower().startswith("re:") else f"Re: {subj}" if subj else "Re:"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        with server:
            server.login(user, config.get("password") or "")
            server.sendmail(user, [to], msg.as_string())
        return True, "已发送。"
    except Exception as e:  # noqa: BLE001
        return False, f"SMTP 发送失败：{e}"
