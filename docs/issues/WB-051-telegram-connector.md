---
id: WB-051
title: 新增 Telegram 连接器（内置 MCP server，Bot API 收发消息）
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/mcp_servers/telegram.py
  - backend/agent/mcp_client.py:43-54,64-76
  - backend/mcp_servers/__init__.py:11-23
  - backend/config.py:56-59
  - backend/.env.example:16-19
  - src/data/catalog.ts:301-321
created: 2026-07-07
---

## 问题

连接器目录里有不少「需 token 的第三方协作/通讯」类连接器（GitHub、企业微信、飞书…），
但当前**真正接了后端 MCP server 的只有** 本地便签 / 时间助手 / 工作区检索 / GitHub
（`READY_CONNECTORS`，`src/data/catalog.ts:320`）。缺一个能让 agent 真实收发 Telegram
消息的连接器。用户要求补上 Telegram。

## 触发场景

用户在项目/会话 loadout 里勾选「Telegram」，希望 agent 能：
- 把一段文本发到指定 Telegram 会话（send_message）；
- 拉取最近收到的消息（get_updates），以便获知对方 chat_id / 回复内容；
- 校验 bot 身份与 token 是否有效（get_me）。
当前勾选「Telegram」是 no-op（后端 `CONNECTORS` 无此项）。

## 影响

P2：功能补全，不影响既有路径。Telegram 是常见的通知/协作出口，接入后 agent 可作为
「本地 → Telegram」的真实发送方，与既有 GitHub 连接器同属「需 token 的第三方 API」族。

## 建议修法

走**路线 B（自写内置 Python FastMCP server）**，而非路线 A（npx 第三方包），理由：
Telegram Bot API 是纯 HTTP，`httpx` 已是后端依赖（`requirements.txt`）；内置 server 进程内
运行 → 打包版可用、无 Node/npx 依赖；`requires` 仍可门控 token。与现有 notes/clock/search
内置样板 + GitHub 的 token 门控组合一致。

1. 新增 `backend/mcp_servers/telegram.py`：`FastMCP("telegram")`，工具用
   **`async def` + `httpx.AsyncClient`**（内置 server 在主事件循环内进程内运行，
   同步阻塞网络请求会卡死事件循环 —— 见 WB-002）。token 在**调用时**从
   `os.environ["TELEGRAM_BOT_TOKEN"]` 读取。工具：`get_me` / `send_message(text, chat_id?)`
   / `get_updates(limit?)`。`send_message` 的 chat_id 缺省时回退到可选的
   `TELEGRAM_CHAT_ID` 环境变量。所有 Telegram API 错误 / 网络错误都返回可读错误串，
   不抛异常拖垮聊天。
2. `backend/agent/mcp_client.py`：`CONNECTORS` 加
   `"Telegram": {"builtin_server": "telegram", "builtin": True, "requires": ["TELEGRAM_BOT_TOKEN"]}`
   （不能用 `_local()`，它不带 `requires`）；`_builtin_fastmcp()` 加 `telegram` 分支。
3. `backend/mcp_servers/__init__.py`：`_SERVERS` 加 `"telegram"`，`run_mcp_server()` 加分支
   （与 notes/clock/search 保持对称）。
4. `backend/config.py`：Settings 加 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`（discoverability）。
5. `backend/.env.example`：加 Telegram 配置注释样例。
6. 前端 `src/data/catalog.ts`：`NP_CONNS` 加 Telegram 一项，加进 `READY_CONNECTORS` 与
   `NEEDS_TOKEN_CONNECTORS`。**name 必须与后端 CONNECTORS 的 key `"Telegram"` 完全一致。**

凭据只加在 `backend/.env`（铁律 4），前端全程只传 `"Telegram"` 名字。

## 验证

- 后端：`python -m py_compile` 改动的 .py 全过。
- 未配 token 时勾选 Telegram → `open_connectors` 应 skip 并给出「需在 backend/.env 配置
  TELEGRAM_BOT_TOKEN」（复用现有 `requires` 门控，参考 test_C_skills_connectors.py C7）。
- 配了真实 token 时：`get_me` 返回 bot 用户名；`send_message` 真发到 Telegram；
  `get_updates` 拉到消息。（无 token / 无网络时至少要能优雅报错，不崩。）
- 前端：`npx tsc --noEmit` 过；连接器面板出现「Telegram」，带「需配置」角标。

## 处理记录（2026-07-07）

- 改动：
  - 新增 `backend/mcp_servers/telegram.py`：`FastMCP("telegram")`，三个 `async` 工具
    `get_me` / `send_message(text, chat_id?)` / `get_updates(limit?)`，`httpx.AsyncClient`
    调 Bot API；token/chat_id 调用时读 `os.environ`；网络/HTTP/API 错误统一降级为可读串
    （`_api` 永不抛异常），文本超 4096 与缺 chat_id 均给明确提示。
  - `backend/agent/mcp_client.py`：`CONNECTORS` 加
    `"Telegram": {"builtin_server": "telegram", "builtin": True, "requires": ["TELEGRAM_BOT_TOKEN"]}`；
    `_builtin_fastmcp()` 加 telegram 分支。
  - `backend/mcp_servers/__init__.py`：`_SERVERS` 加 `"telegram"` + `run_mcp_server()` 分支。
  - `backend/config.py`：Settings 加 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`。
  - `backend/.env.example`：加 Telegram 注释样例。
  - `src/data/catalog.ts`：`NP_CONNS` 加 Telegram（✈️），加进 `READY_CONNECTORS` 与
    `NEEDS_TOKEN_CONNECTORS`。
  - `backend/tests/functional/test_C_skills_connectors.py`：加 C9（Telegram 无 token 未就绪门控，镜像 C7）。
- 验证：
  - `py_compile` 全过；`npx tsc --noEmit` 过。
  - 直连 `open_connectors` 冒烟测试 4/4 通过：① 无 token → skip 且理由含 TELEGRAM_BOT_TOKEN；
    ② 有 token → 进程内发现 get_me/send_message/get_updates 三工具；③ get_me 用无效 token
    真打到 Telegram API 得 401 → 优雅返回「Telegram API 拒绝了请求：Unauthorized」不崩；
    ④ send_message 缺 chat_id → 返回「缺少 chat_id…」提示。
  - 复核 runtime.py:345-346：未就绪连接器渲染为「连接器未就绪 Telegram（…）」，C9 断言成立。
- commit：（未提交）
