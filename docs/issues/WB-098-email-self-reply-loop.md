---
id: WB-098
title: 邮件渠道自我回复循环 —— 助手回信落回收件箱被当新邮件反复处理
severity: P1
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/channels/email_api.py
created: 2026-07-09
---

## 问题

WB-096 邮件渠道：当白名单包含渠道账号自己（如自测：账号 = 白名单 = chenqilscy@gmail.com），
助手用 SMTP 发的回信会落回同一收件箱 → IMAP 下轮把它当未读新邮件拉回 → From 命中白名单 →
再驱动 agent 再回信 → **无限自我回复循环 / 邮件风暴**。真机 Gmail 自测即触发。

## 触发场景

给助理挂邮件渠道，白名单填账号本身，从该账号发一封 → 助手回信到该账号 → 回信被再次收取处理 → 循环。

## 影响

P1：一旦发生就是邮件风暴（对外发信、不可控），必须先修再让用户测。

## 建议修法

给助手发出的回信打一个标记头 `X-WorkBuddy-Assistant: 1`（`email_api.send_reply`），`fetch_unseen`
遇到带此头的邮件直接跳过（那是我们自己发的回信）。这样：用户原始邮件（无此头）正常处理一次；
助手回信（有此头）被收取时跳过，循环打破——且不影响"从账号自己发测试信"。

## 验证

- `py_compile` 通过。
- 真机：从白名单账号发一封 → 助手回信一次 → 不再对自己的回信继续回信（无循环）。

## 处理记录（2026-07-09）

- 改动：`email_api.send_reply` 给回信加 `X-WorkBuddy-Assistant: 1` 头；`fetch_unseen` 遇带此头的邮件
  直接 `continue` 跳过（那是助手自己发的回信）。真机 Gmail 自测（白名单=账号自己）时发现此循环隐患。
- 验证：`py_compile` 通过；重启 :8000 加载。真机自测（用户从 chenqilscy@gmail.com 自发）循环打破待用户发信确认。
- commit：（同 WB-097 之后单独提交）
