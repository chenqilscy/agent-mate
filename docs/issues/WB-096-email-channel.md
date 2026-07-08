---
id: WB-096
title: 助理邮件渠道 —— IMAP 收 + SMTP 发（多渠道新类型，接入多助理）
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/channels/email_api.py
  - backend/channels/manager.py
  - src/lib/api.ts
  - src/components/channel/AssistantChannels.tsx
created: 2026-07-08
---

## 问题 / 目标

多助理·多渠道架构（WB-086~089）里 `email` 是「敬请期待」占位。本 issue 把它做成真渠道类型：
每个助理可挂一个邮件渠道，**IMAP 轮询收件箱 → 路由到该助理跑 agent → SMTP 回复原发件人**。
与 Telegram 渠道完全同构，复用 ChannelManager。

## 建议修法

- `channels/email_api.py`（新）：stdlib imaplib/smtplib/email 封装——`fetch_unseen(config)`（拉未读、
  标记 \Seen、解析 from/subject/text 正文）、`send_reply(config, to, subject, body, in_reply_to)`
  （SMTP：465→SSL / 其它→STARTTLS）、`verify(config)`（试登录）。阻塞库，由 manager 用 `asyncio.to_thread` 包。
- `channels/manager.py`：
  - `_email_poll_loop(ch_id)`：每 ~45s `to_thread(fetch_unseen)` → 逐封 `_handle_email`。
  - `_authorize_email(ch, from)`：白名单 allow_from（逗号分隔）或首发件人配对；可选**暗号**（subject/body
    含 secret 才处理，抗 From 伪造）。发件人邮箱 = 会话键（channel_chat_sessions.chat_id）。
  - `_handle_email`：鉴权 → 映射会话 → `_run_agent`（该助理 loadout/工作空间/mode）→ `to_thread(send_reply)`。
  - 泛化 `_channel_should_run` / `refresh` 按 type 分发 poller；`_run_signature` 让 config 变更重启 poller。
  - `channel_public`：email 回 `config`（本机可见，含账号/密码——延续 WB-093 本机可见）。
  - `CHANNEL_TYPES` 里 email 置 `available: True`。
- 前端：`AssistantChannel` 增 `config`；`AssistantChannels.tsx` 加 EmailChannelForm（IMAP/SMTP host·port/
  账号/应用密码/白名单/暗号 + 服务商预设 Gmail/Outlook/QQ/163）；按 type 分发表单；列表行支持 email。

## 安全说明

邮件 From 可伪造，白名单是弱保护；提供可选**暗号**（只处理主题/正文含暗号的邮件）加固。凭据存 DB
per-channel（同 bot token，本机可见，DB gitignore）。

## 验证

- `py_compile`/`tsc`/`vite build` 通过。
- 真机（用户给一个开了 IMAP/SMTP + 应用密码的邮箱）：给助理挂邮件渠道 → 从白名单地址发一封 → 助理
  IMAP 收到 → 跑 agent → SMTP 回信到原发件人；换 config 重启 poller；非白名单/无暗号被忽略。

## 处理记录（2026-07-08）

- 改动：新 `channels/email_api.py`（stdlib imaplib/smtplib/email：`fetch_unseen`(拉未读+标记已读+
  正文取 text/plain 优先·HTML 粗转·去引用)、`send_reply`(465→SSL/其它→STARTTLS)、`verify`；IMAP 连接
  30s 超时防卡）；`channels/manager.py` 加 `_authorize_email`(白名单+暗号+首配对)/`_handle_email`/
  `_email_poll_loop`(每 45s `to_thread(fetch_unseen)`)，泛化 `_channel_should_run`/`refresh`(`_run_signature`
  +`_make_loop` 按 type 分发 poller)，`channel_public` 邮件回 config(本机可见)，`CHANNEL_TYPES` email
  置 available；前端 `AssistantChannel` 增 config，`AssistantChannels.tsx` 拆 Telegram/Email 两个表单 +
  通用 Modal 壳 + 类型分发 + 服务商预设(Gmail/Outlook/QQ/163) + 列表行支持 email。
- 验证：`py_compile`/`tsc`/`vite build` 通过。离线 8 项（正文去引用/去HTML、白名单、暗号、不同助理
  各自会话、按渠道锁定、should_run 需齐凭据、channel_public 回 config、类型注册表 available）全过。
  重启 :8000：`/channels/types` email available；POST 邮件渠道→创建成功/config 含账号密码回传(本机可见)/
  running 随停用为 False；GET 回传 config；DELETE 清理。
- 待用户：真机 IMAP/SMTP 收发（需你一个开了 IMAP/SMTP + 应用密码的邮箱）；机制已全验，凭据待用户。
- commit：（尚未提交）
