---
id: WB-077
title: 助理设置面板 —— 齿轮点开的真配置（名字/人格/模型/开关/绑定/token 存 DB）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/AssistantView.tsx:88
  - backend/channels/telegram_bridge.py:1
  - backend/routers/channels.py:1
  - backend/storage/db.py
  - backend/agent/runtime.py:174
created: 2026-07-08
---

## 问题

WB-072 Slice 2 让助理页显示真实状态与真会话，但**没有页面内配置**：右上角 ⚙️ 齿轮只弹
信息 toast（[AssistantView.tsx](../../src/views/AssistantView.tsx) `onGear`），助理的名字/人格/模型/
开关/绑定 chat 都只能改 `backend/.env` 再硬重启后端。原型里"给助理起名字、定风格"是占位。

本 issue 把齿轮做成真的**助理设置**面板（单助理），可在 UI 配置：助手名字、人格/风格、模型、
运行开关（免改 .env/重启）、查看与解绑绑定的 Telegram chat，以及 bot token。

## 触发场景

1. 助理页点 ⚙️ → 打开「助理设置」弹窗。
2. 填名字「小助」、人格「简洁、条列、结论先行」、选模型、粘贴 bot token、开启 → 保存。
3. 后端持久化到 DB；桥接按新 token/开关即时启停；此后 Telegram/App 的回复都带该人格与名字。
4. 点「解绑」→ 清除绑定，下一个 /start 重新配对。

## 影响

P2：让"助理"从只能改文件配置，变成产品内可配置的真功能，兑现原型的助手个性化承诺。增量、
默认不改变既有行为（DB 空时回退 .env）。

## 建议修法

**后端**
- `storage/db.py`：新增 `assistant_settings(owner_id PK, bot_token, name, persona, model, enabled, updated_at)`
  + `get_assistant_settings` / `upsert_assistant_settings`（部分字段合并）。
- `channels/telegram_api.py`：`set_token_override()` + `token()` 改为「override(来自 DB) 优先，否则 .env」，
  保持依赖极简（不 import db）。
- `channels/telegram_bridge.py`：`_apply_config()`（把 DB token 灌进 override + 读人格）、
  `effective_enabled()`（有 token 且 DB.enabled(有则用，否则回退 env 开关)）、`refresh()`（应用配置 +
  按 effective 启停）、`status()`/`say()`/`_run_agent` 带上 name/persona 注入。
- `agent/runtime.py`：`run_chat` 加可选 `system_extra`（附加到 system_prompt，注入助理人格），
  默认 None、不影响既有调用方。
- `routers/channels.py`：`GET` 扩展返回 config（name/persona/model/has_token/enabled，**绝不含 token 值**）；
  新增 `PATCH /api/channels/telegram/config`（name/persona/model/enabled/token；token write-only）、
  `POST /api/channels/telegram/unbind`。
- `main.py` startup 改为 `telegram_bridge.refresh()`（兼顾 DB + .env）。

**前端**
- `lib/api.ts`：扩展 `TelegramChannel`（config 字段）+ `patchTelegramConfig` / `telegramUnbind`。
- 新 `components/.../AssistantSettingsModal.tsx`：复用 `.np-*` 弹窗类（自带暗色）；字段=名字/人格/模型/
  token(password，占位「已配置则留空不改」)/开关/绑定 chat 显示+解绑。
- `AssistantView.tsx`：齿轮改为打开该弹窗；保存后刷新状态。

## token 处理（**用户显式决定，偏离铁律#4 字面**）

用户（项目 owner）明确选择：**token 存数据库、不用 .env**。据此实现，但保留铁律#4 的核心安全属性：
- token **只存后端**（DB，`*.db*` 已被 .gitignore，永不提交）；
- **write-only**：`GET`/config 只回 `has_token` 布尔，**绝不把 token 值回传前端**；
- `.env` 的 `TELEGRAM_BOT_TOKEN` 保留为回退（DB 空时用），既有部署零变化。

> 建议：回头把 CLAUDE.md 铁律#4 措辞从"只存 .env"更新为"后端-only（DB 或 .env），绝不进前端/提交"，
> 使文档与此决定一致。

## 验证

- `npx tsc --noEmit`、`npx vite build` 通过；改动的后端 `py_compile` 通过。
- DB 空 + .env 有 token：行为同 WB-072（回退），回归不破。
- UI 设 token/开关/名字/人格 → 保存 → `status` 反映；Telegram/App 回复带人格；`GET` 不含 token 值。
- 解绑后下一个 /start 重新配对。
- 明暗双主题看弹窗（复用 `.np-*`，天然暗色）。

## 处理记录（2026-07-08）

- 改动：
  - `agent/runtime.py`：`run_chat` 加可选 `system_extra`，附加到 system_prompt（注入助理人格），
    默认 None 不影响既有调用方。
  - `storage/db.py`：`assistant_settings` 表 + `get_assistant_settings` / `upsert_assistant_settings`
    （部分字段合并）+ `clear_channel_bindings`（解绑）。
  - `channels/telegram_api.py`：`set_token_override()` + `token()` 改为「DB override 优先，否则 .env」，
    保持只依赖 os+httpx。
  - `channels/telegram_bridge.py`：`_persona_text()`/`_model()`（注入名字/风格/模型）、`effective_enabled()`
    （token(DB 或 .env) 且 enabled(DB 优先，NULL 回退 env)）、`_apply_config()`、`refresh()`（应用配置 +
    干净重启，换 token 后重跑 getMe/deleteWebhook）、`get_config()`、`set_config()`、`unbind()`；`status()`
    带 running + 配置字段（**绝不含 token 值**）。
  - `routers/channels.py`：`GET` 统一经 `_with_messages` 返回状态+config+transcript；新增
    `PATCH /telegram/config`（name/persona/model/enabled/token；token write-only、非空才写）、
    `POST /telegram/unbind`。`main.py` startup 改 `telegram_bridge.refresh()`（兼顾 DB+.env）。
  - 前端：`lib/api.ts` 扩展 `TelegramChannel`（running/name/persona/model/enabled_override）+
    `patchTelegramConfig`/`telegramUnbind`；新 `components/channel/AssistantSettingsModal.tsx`（复用 `.np-*`）；
    `AssistantView.tsx` 齿轮改为打开设置弹窗，未配置引导指向 ⚙️。
- token 处理：按用户显式决定**存 DB**（write-only、绝不回传前端、DB 已 gitignore；.env 作回退）。**偏离铁律#4
  字面**——建议把 CLAUDE.md 铁律#4 措辞改为「后端-only（DB 或 .env），绝不进前端/提交」。
- 验证：
  - `py_compile` 全过；`npx tsc --noEmit`、`npx vite build` 通过。
  - 硬重启 :8000 加载新代码，真机端点实测：① `GET` 返回新配置字段；② `PATCH {name:小助,persona,enabled:false}`
    → `running:false/connected:false`（**开关实时停桥接**），再 `enabled:true` → `running:true`（实时起）；
    ③ `PATCH {token:<真 token>}` 写入 DB → `connected:true @CkyBuddyBot`（**DB token 路径真机连通**）；
    ④ token 泄漏检查：任何响应都搜不到 token（**write-only 不回传**）；⑤ `POST /say「你叫什么名字」`
    → 「我叫小助…」（**人格注入端到端生效**）。
  - 未跑：浏览器明暗双主题实时截图（Playwright profile 被占用）；弹窗复用 `.np-*` 天然暗色，无新增风险色。
- commit：（尚未提交）
