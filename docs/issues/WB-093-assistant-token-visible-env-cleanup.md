---
id: WB-093
title: 助理渠道 token 本机可见（撤销 write-only）+ 移除 .env Telegram 配置 + 铁律#4 同步
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/channels/manager.py
  - src/lib/api.ts
  - src/components/channel/AssistantChannels.tsx
  - backend/.env
  - CLAUDE.md
created: 2026-07-08
---

## 问题 / 决策

用户（项目 owner）显式要求：**在本机设置 UI 里能看到并编辑原始 bot token**（撤销 WB-077 的
write-only：之前后端绝不回传 token 值），并**删除 backend/.env 里的 Telegram 配置项**（token 已在
DB，管理器从渠道 config 读，删 .env 不影响运行）。

理由与边界：这是 local-first 本机应用，后端只绑 `127.0.0.1`、DB 已 `.gitignore`（绝不提交），
token 不出本机；在自己机器的设置里可见可改是合理选择。**LLM API Key 不在此列**——仍严格
只存 .env、绝不进前端（铁律#4 的强约束保留）。

## 建议修法

- `channels/manager.py`：`channel_public()` 增 `token` 字段回传真实 token 值（供本机设置 UI 显示）。
- `lib/api.ts`：`AssistantChannel` 增 `token: string`。
- `components/channel/AssistantChannels.tsx`：ChannelForm 预填 token（可见，带显示/隐藏切换），
  保存时回传。
- `backend/.env`：删 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_ASSISTANT` 三行 + 注释
  （LLM/HUB 等保留）。
- `CLAUDE.md` 铁律#4：措辞同步为「LLM API Key 只存 .env、绝不进前端；连接器/机器人 token 存后端 DB
  （gitignore、不提交），local-first 本机设置 UI 内可见可改」。

## 验证

- `py_compile` / `tsc` / `vite build` 通过。
- 重启 :8000（.env 已无 telegram）：`/assistants` 里各渠道回 `token` 真值；@CkyBuddyBot / @CqBuddybot
  仍 running（token 来自 DB，删 .env 不影响）。
- 设置 UI 编辑渠道能看到并改 token。

## 处理记录（2026-07-08）

- 改动：`manager.channel_public()` 增 `token` 字段（本机可见）；`lib/api.ts` `AssistantChannel` 增
  `token`；`AssistantChannels.tsx` ChannelForm 预填 token + 显示/隐藏切换；`backend/.env` 删
  `TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID/TELEGRAM_ASSISTANT`（改成一行说明，token 已在 DB）；
  `CLAUDE.md` 铁律#4 措辞同步（LLM Key 仍严格不进前端；bot/连接器 token 存 DB、本机 UI 可见可改）。
- 验证：`py_compile`/`tsc`/`vite build` 通过。重启 :8000（.env 已无 telegram）：两 bot 仍 `running=True`
  （小助 @CkyBuddyBot / 研究员 @CqBuddybot，token 从 DB 读，删 .env 无影响）；`/assistants` 各渠道回真实
  `token` 值（设置 UI 可预填显示）。`.env` 为 gitignore、其改动只在本机不进 commit。
- commit：（尚未提交）
