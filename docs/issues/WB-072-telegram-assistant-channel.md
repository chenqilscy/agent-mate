---
id: WB-072
title: 助理外部渠道（一）—— Telegram 长轮询桥接：收发消息驱动真实 agent
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - src/views/AssistantView.tsx:8
  - backend/mcp_servers/telegram.py:1
  - backend/agent/scheduler.py:1
  - backend/config.py:62
  - docs/workbuddy-实现方案.md:257
created: 2026-07-08
---

## 问题

「助理页」（[AssistantView.tsx](../../src/views/AssistantView.tsx)）定位是**让 AI 助手通过外部渠道触达用户**，
但当前是纯原型占位：三条写死的 canned 消息、假的连接状态 `🟢 微信小程序`、`onSend` 只弹
`toast('助理外部渠道连通功能将在 M5 落地')`（[AssistantView.tsx:52](../../src/views/AssistantView.tsx#L52)）。
方案 [workbuddy-实现方案.md:257](../../docs/workbuddy-实现方案.md#L257) 将其标为 P2/M5+，一直未落地。

企业微信/WhatsApp 依赖用户不具备的渠道凭证，本期**只做 Telegram**：把 Telegram 收到的消息
接入既有 agent 工具循环 [runtime.run_chat()](../../backend/agent/runtime.py#L174)，再把回复发回 Telegram。

根因/约束：后端是 local-first 的 localhost 服务（`127.0.0.1:8000`），Telegram `setWebhook`
需要**公网 HTTPS 地址**才能被 Telegram 服务器回调——localhost 收不到。因此本期用
**长轮询 `getUpdates`（后端主动拉）**，与现有 [telegram.py](../../backend/mcp_servers/telegram.py) 的调用方式、
[scheduler.py](../../backend/agent/scheduler.py) 的后台任务范式完全同构。Webhook 路由留待将来有公网地址/经 Hub 转发时再加。

## 触发场景

1. 用户在 `backend/.env` 配 `TELEGRAM_BOT_TOKEN`（@BotFather 申请）并开 `TELEGRAM_ASSISTANT=1`。
2. 用户在 Telegram 给 bot 发 `/start` → 后端把该 chat 绑定为主人（若 `.env` 未预设 `TELEGRAM_CHAT_ID`）。
3. 用户发「帮我把 workspace 里的 todo 整理成清单」→ 后端长轮询收到 → 驱动真实 agent → 回复发回 Telegram。
4. 非绑定用户给 bot 发消息 → 一律忽略（安全门）。

## 影响

P2：这是原型里承诺、方案里排期但从未落地的一整个一级视图的核心能力。做完即让 WorkBuddy 的
助手能从桌面 App 之外（手机 Telegram）被驱动，是「助理」概念的第一次真正兑现。属增量新能力，
默认关（未配 token/未开开关时零变化，纯本地全功能不受影响）。

## 建议修法

**Slice 1（本 issue 主体，后端闭环）**

1. 新增 `backend/channels/telegram_bridge.py`：一个后台 asyncio 长轮询任务，仿 [scheduler.py](../../backend/agent/scheduler.py)：
   - `getUpdates` 带 `offset`（消费/ack 已处理 update）+ `timeout=30`（长轮询，近实时、省流量）。
   - 复用 [telegram.py](../../backend/mcp_servers/telegram.py) 的 `_api()`（永不抛异常）与 4096 分片逻辑；
     Bot API 调用抽到可共享的 helper，避免与 MCP server 重复实现。
   - **鉴权**：白名单 + `/start` 配对。`.env` 有 `TELEGRAM_CHAT_ID` 就只认它；没设则第一个发 `/start`
     的 chat 自动绑定为主人并持久化锁定；其余 chat 一律忽略。
   - **会话映射**：新增极小表 `channel_sessions(channel, chat_id, session_id, owner_id, created_at)`，
     `chat_id ↔ session_id` 一对一，续聊不断线（一个 Telegram 会话 = 一个长期 WorkBuddy 会话，kind=`assistant`）。
   - **驱动**：headless 消费 `run_chat(session, user, text)`（同 scheduler：`async for _ in ...: pass`），
     完成后取该会话最后一条 assistant 消息 `db.list_messages()` 作为回复文本，`sendMessage` 发回（>4096 分片）。
   - 防重叠（同一 chat 串行）、单条超时、错误隔离（一条消息失败不杀循环）。
2. 配置门控：仅当 `TELEGRAM_BOT_TOKEN` 且 `TELEGRAM_ASSISTANT=1` 时在 `main.py` startup 启动桥接（默认关）。
   在 [config.py](../../backend/config.py) 加 `TELEGRAM_ASSISTANT` 开关；`.env.example` 补注释。
3. 铁律遵守：token 只在后端 `.env`、绝不进前端/子进程；agent 在既有沙箱内执行（`run_chat` 已按 project 切根）。

**Slice 2 / 3（另开 issue 或本 issue 后续）**：AssistantView 接真实 bot 状态+真会话历史；`POST /api/channels/telegram/webhook` 供公网/Hub 部署。

## 验证

- `cd backend && ./.venv/Scripts/python.exe -m py_compile` 改动文件通过。
- 未配 `TELEGRAM_BOT_TOKEN` / 未开 `TELEGRAM_ASSISTANT`：后端启动无桥接任务、日志无异常、纯本地全功能不变（回归）。
- 配好 token + chat_id（或走 `/start` 配对）：给 bot 发一条消息，收到由真实 LLM 生成的回复；
  连发两条，第二条能延续上下文（同一会话）；发 >4096 字符的长回复被正确分片。
- 非绑定 chat 发消息被忽略（日志可见「忽略未授权 chat」）。
- 桥接崩一条消息（如 LLM 未配置）不影响后续消息与其它 SSE 流。

## 处理记录（2026-07-08）

- 改动（Slice 1，后端闭环）：
  - 新增 `backend/channels/` 包：
    - `telegram_api.py` —— 底层 Bot API 客户端（`api/get_me/get_updates/send_message/chunk_text`）。
      与 `mcp_servers/telegram.py` 同源但**长轮询感知超时**（读超时 = poll timeout+余量，否则长轮询被提前掐断），
      依赖极简（os+httpx），故与「独立 stdio 子进程」形态的连接器解耦、单独一份。
    - `telegram_bridge.py` —— 后台长轮询任务，仿 `agent/scheduler.py`：`getUpdates(offset,timeout=30)` 长轮询 →
      `_authorize_and_get_session`（白名单+/start 配对）→ 映射到长期会话（kind=assistant）→ headless 驱动
      `runtime.run_chat` → 取本轮新产生的末条 assistant 消息发回（>4096 分片）。防重叠(`_busy`)、单条超时、
      错误隔离、游标先进 at-most-once（重启不重复执行副作用）。
  - `storage/db.py`：新增 `channel_sessions`(chat_id↔session_id，兼作白名单) + `channel_state`(轮询游标) 两张表，
    及 `get/first/bind_channel_session`、`get/set_channel_offset` helper。
  - `config.py`：新增 `TELEGRAM_ASSISTANT` 开关 + `telegram_assistant_enabled` 门控属性（须 token 且开关同时具备）。
  - `main.py`：startup/shutdown 按门控 start/stop 桥接（默认关，纯本地零变化）。
  - `.env.example`：补 `TELEGRAM_ASSISTANT` 开关与配对/白名单说明。
  - 真机验证中补的产品级修复：桥接启动时自动 `deleteWebhook`（长轮询与 webhook 互斥，
    旧 bot 设过 webhook 会导致 getUpdates 409）——`telegram_api.delete_webhook()` + `_loop` 启动调用。
- 验证：
  - `py_compile` 全部改动文件通过；`import main` 无误、默认关闭时无桥接任务、73 路由挂载正常（回归）。
  - 离线单测（隔离 DB）：门控默认关；`channel_state` 游标往返；未设 CHAT_ID 时首个 chat 配对+续聊复用+锁定他人；
    绑定持久化；会话 kind=assistant 真入库；设 CHAT_ID 时只认它；chunk_text 4096 分片。全过。
  - 端到端主链路（monkeypatch `tg.get_updates/send_message` + `runtime.run_chat`，无网络/LLM）跑 `_handle_update`：
    ①授权+驱动+回复 ②/start 欢迎语不跑 agent ③续聊复用会话、/start 未入 agent ④未授权 chat 被忽略
    ⑤非文本消息明确提示。5 场景全过。
  - **真机 smoke —— 已通过（2026-07-08，bot @CkyBuddyBot）**：`/start` → 秒回欢迎语 + 绑定 chat_id=8617683065
    建会话；连发「你是？」「你当前用什么模型?」「今年的足球世界杯…」每条都命中 api.deepseek.com 生成真实
    Markdown 回复并发回；同一会话多轮 user/assistant 连续（续聊不断线）。全链路入站→驱动本机 agent→回复
    发回真机跑通。
- 运营注意（Telegram 约束）：
  - **单实例**：同一 bot 只允许一个 getUpdates 轮询者，多实例并发会 `409 Conflict: terminated by other
    getUpdates request`。生产即由后端自带桥接独占轮询——别再另起第二个轮询进程。
  - **webhook 互斥**：bot 若设过 webhook，长轮询会 409；桥接启动已自动 deleteWebhook 兜底。
- 备注：本 issue = Slice 1（后端闭环，已完成并真机验证）。Slice 2（AssistantView 接真状态+真会话历史）、
  Slice 3（`POST /api/channels/telegram/webhook` 供公网/Hub 部署）另开 issue 推进。assistant 会话是真实
  会话，会出现在会话列表里（铁律#1 真持久化）——Slice 2 会把它收敛进助理页展示。
- commit：（尚未提交）
