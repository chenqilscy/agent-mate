---
id: WB-087
title: 多助理 S1 —— 后端数据模型 + CRUD + 多 bot 渠道管理器 + 迁移
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/storage/db.py
  - backend/agent/sandbox.py
  - backend/agent/runtime.py
  - backend/channels/telegram_api.py
  - backend/channels/manager.py
  - backend/routers/channels.py
  - backend/main.py
created: 2026-07-08
---

## 问题

WB-086 epic 的 S1：把单助理后端泛化为多助理 + 多渠道的数据模型与运行时。见
[`docs/workbuddy-助理-架构设计.md`](../workbuddy-助理-架构设计.md) §3/§5/§6。

## 建议修法

- `db.py`：`assistants` + `channels` + `channel_chat_sessions`（channel_id 键）三张新表 + CRUD helper；
  `_migrate_assistants()` 把 WB-077 的 `assistant_settings` + `channel_sessions` 非破坏迁移为
  一条默认助理 + 一条 Telegram 渠道（保住 @CkyBuddyBot）。
- `sandbox.py`：`assistant_root(id)` → `workspace/assistants/<id>/`（助理专属工作空间）。
- `runtime.py`：`run_chat` 加可选 `workspace`（default/project:<id>/dedicated 覆盖根）+ 复用 plan/ask 承载 mode。
- `telegram_api.py`：从「全局 token override」改为**每次调用显式传 token**（多 bot 并存）。
- `channels/manager.py`（新）：ChannelManager —— 每个启用的 Telegram 渠道一个 poller，reconcile 启停；
  入站消息 → 鉴权 → 路由到其助理 → 用助理 loadout/工作空间/mode 驱动 `run_chat` → 原渠道回复。
  另含 App 面向：assistants/channels CRUD 封装、status(assistant)、say(assistant,text)。
- `routers/channels.py`：新增 `/api/assistants` 及其 `/channels` 子资源 CRUD；旧 `/channels/telegram*`
  端点保留为**兼容层**映射到默认助理（保证 WB-077 前端在 S2 落地前仍可用）。
- `main.py` startup 改 `manager.refresh()`。

## 验证

- `py_compile` 全过；迁移后现有 @CkyBuddyBot 仍轮询、仍能收发（真机）。
- 离线：建第二个助理 + 第二个 Telegram 渠道，manager 起两个 poller；两 bot 各路由到各自助理。
- 旧 `/channels/telegram` 兼容端点仍返回默认助理状态（WB-077 前端不炸）。

## 处理记录（2026-07-08）

- 改动：
  - `db.py`：`assistants` / `channels` / `channel_chat_sessions`（channel_id 键）三表 + 全套 CRUD helper；
    `_migrate_assistants()` 把 WB-077 `assistant_settings` + `channel_sessions` 非破坏迁移为
    一条默认助理 + 一条 Telegram 渠道（复用旧 assistant 会话、迁绑定与游标）。
  - `sandbox.py`：`assistant_root(id)` + `workspace_root(spec, project_id)`（default/project:<id>/dedicated:<id>）。
  - `runtime.py`：`run_chat` 加可选 `workspace` 覆盖（走 `workspace_root`），mode 复用 plan/ask。
  - `telegram_api.py`：改为**每次调用显式传 token**（多 bot 并存），去掉全局 override。
  - `channels/manager.py`（新）：ChannelManager —— 每个「启用且类型可用」渠道一个 poller，`refresh()`
    协调（启新/停删/换 token 重启）；入站 → 按渠道鉴权(白名单+/start 配对) → 路由到助理 → 用其
    loadout/工作空间/mode 驱动 `run_chat` → 原渠道回复；App 面向 `assistant_public`/`channel_public`
    （绝不含 token）/`say`；`CHANNEL_TYPES` 类型注册表（仅 telegram available）；兼容层 compat_*。
  - `routers/channels.py`：旧 `/channels/telegram*` 兼容映射到主助理；新 `/assistants*`（CRUD + say +
    `/channels` 子资源 CRUD + unbind）+ `/channels/types`。删除 `telegram_bridge.py`；`main.py` startup 改 `manager.refresh()`。
- 验证：
  - `py_compile` 全过。离线（隔离 DB）：fresh 零变化；迁移单助理→assistant+channel+绑定+游标（幂等）；
    多助理 CRUD；`assistant_public`/`channel_public` 不泄漏 token；**同 chat_id 跨渠道各自独立会话**（证明
    按 channel_id 键）+ 已配对渠道锁定；渠道白名单；`workspace_root` 解析；poller 协调 4→3→2→0。全过。
  - 真机（重启 :8000 加载 S1，跑现有 DB）：迁移把 WB-077「小助」搬成 assistant + telegram 渠道
    `running/connected @CkyBuddyBot bound=8617683065`；日志见 poller 干净启动（getMe/deleteWebhook 200）无异常；
    `/api/channels/telegram` 兼容端点仍返 WB-077 结构（16 条 transcript）；无 token 泄漏。
- 备注：S2（WB-088 前端多助理管理 UI）落地后，旧 `/channels/telegram*` 兼容层可移除。
- commit：（尚未提交）
