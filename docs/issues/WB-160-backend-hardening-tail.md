---
id: WB-160
title: 后端加固尾集 —— 通知空 ids 误清全部 / MCP 连接超时孤儿子进程 / 邮件批量先标已读丢信 / 流出错丢半截回复 / web_fetch SSRF / skillhub slug 校验
severity: P2
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/storage/db.py:1559
  - backend/agent/mcp_client.py:214
  - backend/channels/email_api.py:98
  - backend/agent/runtime.py:567
  - backend/agent/skills.py:27
  - hub/skillhub_client.py:283
created: 2026-07-14
---

## 问题

一组独立的中低危加固项：

1. **`db.py:1559` `mark_notifications_read` 空 ids 误清全部（P2）**：守卫 `if ids:`，空列表落 else 分支 → 标记**所有**通知已读。`notifications.py` 直传 `body.ids`，客户端发 `{"ids":[]}` 会清空全部未读。
2. **`mcp_client.py:214-228` 连接超时孤儿子进程（P2）**：`_connect` 在 `stack.enter_async_context(stdio_client(...))`（已 spawn 子进程）后被 `wait_for` 超时取消，若清理尚未注册到 `stack`，后续 `aclose()` 不会杀该进程 → 每次超时泄漏一个进程。
3. **`email_api.py:98-131` 批量先标已读丢信（P3）**：`fetch_unseen` 用 `(RFC822)` 取信立即置 `\Seen`；鉴权+agent 运行在其后。处理 #1 时崩溃/重启，#2–10 已 `\Seen` 永不重取 → 静默丢邮件。
4. **`runtime.py:567-578` 流出错丢半截回复（P3）**：`LLMError`/异常中途 yield error+done 后 `return`，位于其后的 `db.add_message(assistant)` 永不执行 → 已流式给用户的文本不入库，reload 后消失。
5. **`skills.py:27/170` web_fetch/html_to_markdown 无 SSRF 守卫（P3）**：LLM 给的 URL 仅校验 http(s) scheme，不挡 loopback/私网/link-local；可能被入站邮件/Telegram 内容诱导打内网。
6. **`hub/skillhub_client.py:283` slug 未校验（P3）**：`slug` 从 `/catalog/skills/{slug}/preview` 路径原样拼进 `tmp/slug/SKILL.md` 与 `install slug` 子进程参数，路径穿越面。

## 影响

各自独立、中低危；合并为一组加固修。

## 建议修法

1. `mark_notifications_read`：`ids is None` 才「标全部」，空列表 no-op。
2. `_connect`：在 `_connect` 内用局部 `AsyncExitStack`，超时/异常路径显式 `aclose()`（或 push kill 回调）。
3. `fetch_unseen`：用 `BODY.PEEK[]` 取信不置 Seen；成功处理后再 `STORE +FLAGS \Seen`。
4. runtime except 分支：return 前持久化已有的 `assistant_text`/`trace`（或移进 finally）。
5. `skills`：解析 host，拒 loopback/RFC1918/link-local（重定向后复检）。
6. `skillhub_client`：`slug` 先过 `^[A-Za-z0-9._-]+$`，拒路径分隔符/`..`。

## 验证

- `py_compile`（backend + hub）。
- 逐条：`{"ids":[]}` 不清全部；超时连接器不留进程；邮件崩溃重启后 #2–10 仍未读可重取；流中断后 reload 仍见半截回复；`web_fetch("http://127.0.0.1:...")` 被拒；带 `../` 的 slug 被拒。

## 处理记录（2026-07-14）

已修 6 项中的 5 项，邮件 1 项 **deferred**（见下）：

- ✅ **通知空 ids**：`backend/storage/db.py` `mark_notifications_read` 改 `if ids is None:` 标全部、`elif ids:` 标指定、`[]` no-op。
- ✅ **MCP 超时孤儿**：`backend/agent/mcp_client.py` `_connect` 用局部 `AsyncExitStack`，`except BaseException: await local.aclose(); raise`；成功后 `stack.enter_async_context(local)` 交 run 级 stack。超时取消会在本地 stack 就地终止子进程。
- ✅ **流出错丢回复**：`backend/agent/runtime.py` 加 `_persist_partial()`，两个 except 分支 return 前持久化已流式的 assistant_text/trace，`done(mid)` 带回 message_id。
- ✅ **SSRF**：`backend/agent/skills.py` 加 `_is_blocked_host`（getaddrinfo + ipaddress 判 loopback/私网/链路本地/保留/组播/未指定）+ `_guarded_get`（http(s)、逐跳重定向校验）；`web_fetch`/`html_to_markdown` 改走它。
- ✅ **skillhub slug**：`hub/skillhub_client.py` 加 `_SLUG_RE=^[A-Za-z0-9._-]+$` + `_valid_slug`（拒 `..`），`preview()` 入口校验。
- ⏸ **邮件先标已读丢信**：deferred。完整修法需把 `\Seen` 推迟到 manager 里 agent 处理完成后按 Message-ID reconnect+STORE；若该 IMAP SEARCH/STORE 有环境差异会导致每轮重复回复用户（reply spam），比原 bug 更糟，且此处无 live IMAP 可验证。留待可实测 IMAP 时再做。

- 验证：py_compile（backend+hub）+ tsc 过；`_is_blocked_host` 对 localhost/127.0.0.1/169.254.169.254/10.x/192.168.x/::1/0.0.0.0 全 True、8.8.8.8 False；`_guarded_get('http://127.0.0.1:8000/...')` 抛「拒绝访问本机/内网」。
- 状态：`in-progress`（邮件项 deferred，其余已修）。
- commit：未提交（待用户确认）。
