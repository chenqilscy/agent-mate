---
id: WB-086
title: 多助理 · 多渠道 —— 助理子系统重构（总纲 / epic）
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - docs/agentmate-助理-架构设计.md
  - backend/channels/telegram_bridge.py
  - backend/channels/telegram_api.py
  - backend/routers/channels.py
  - backend/storage/db.py
  - src/views/AssistantView.tsx
  - src/components/channel/AssistantSettingsModal.tsx
created: 2026-07-08
---

## 问题 / 目标

现有助理是**单助理 / 单渠道 / 单配置**（WB-072 桥接 + WB-077 设置面板）。用户诉求把它泛化为
**多助理 + 多渠道** 子系统：

1. 支持配置多个渠道；
2. 支持添加多个助理，每个助理设置独立的（多个）渠道；
3. 每种渠道的配置因类型而不同；
4. 每个助理独立设置 指令 / 技能 / 连接器 / 专家 / 大模型 / 权限 / 工作空间；
5. 完善的 UI。

权威设计见 [`docs/agentmate-助理-架构设计.md`](../agentmate-助理-架构设计.md)。

## 已定决策（本 epic 的边界）

- **助理 = 新建独立 `assistants` 实体**（+ `channels`），复用 Project 的 loadout/沙箱**机制与 UI 组件**，
  但与协作（成员/看板）解耦。
- **权限 = 映射 `run_chat` 的 执行 / 计划(plan) / 问答(ask) 三态**，不新造细粒度工具权限门（后端零新增权限逻辑）。
- **只有 Telegram 真跑**：多渠道 = 多个 Telegram bot + 可扩展类型结构；其它渠道类型做成明确
  「敬请期待」占位，不造假（铁律#1）。
- token 存 DB、write-only、绝不回传前端（延续 WB-077）。

## 影响

P1：这是「助理」从演示级单例走向可用产品能力的关键重构，会**泛化重构** WB-072/077
（单助理成为「一个助理 + 一个渠道」特例），须保证迁移后现有 @CkyBuddyBot 仍可用。

## 分片（子 issue，逐片实现、逐片验证、逐片提交）

- **WB-087 · S1（backend）**：`assistants`+`channels` 表 + 泛化 `channel_sessions/state` + CRUD API +
  ChannelManager（多 bot 并存，各自 token/游标/poller）+ `run_chat` 接 workspace/mode 覆盖 +
  `telegram_api` 改「每次调用显式传 token」+ 单助理非破坏迁移。
- **WB-088 · S2（frontend）**：「助理」页重构为主从视图——助理列表 + 新建 + 设置 tab
  （指令/模型/权限/工作空间 + 专家·技能·连接器 挑选器）+ 对话 tab（复用 WB-072/085）。
- **WB-089 · S3（fullstack）**：渠道 tab —— 类型化渠道 CRUD UI（Telegram 表单 + 其它类型占位）+
  入站路由端到端真机验证（多 bot）。
- **WB-090 · S4（fullstack）**：打磨 + 迁移收尾 + 明暗双主题 + 多 bot 真机验证 + 台账/文档收口。

> 子 issue 文件在开工对应片时再建（避免与并发会话抢号）。

## 收口（2026-07-08，已完成）

- **WB-087（S1）** ✅ 后端模型 + CRUD + 多 bot 管理器 + 迁移（commit 69db4bf）。
- **WB-088（S2）** ✅ 前端主从多助理 UI，合并 S3 的渠道管理 UI（commit 0aeb16f）。
- **WB-089（S3 路由验证 + S4 清理）** ✅ 移除兼容层 + epic 级验证收口；原 WB-090 并入本片。
- 结果：可建多个助理、每个独立 loadout(指令/技能/连接器/专家/模型/权限=Plan·Ask·执行/工作空间) +
  独立多渠道（Telegram 真跑，其它类型「敬请期待」占位）；现有单助理「小助」非破坏迁移、@CkyBuddyBot 照常。
- 待用户：第二个真实 Telegram bot 的实机路由（机制已由离线「同 chat_id 跨渠道独立会话」+ poller 协调证明）。

## 验证（epic 级）

- 每片按其子 issue 的「验证」核对；`tsc`/`vite build`/`py_compile` 全过。
- 迁移后现有单 Telegram 助理（@CkyBuddyBot）零感知继续可用。
- 能建第二个助理、挂第二个 Telegram bot、两个 bot 各自路由到各自助理的 loadout/工作空间、互不串扰。
- 明暗双主题过一遍新 UI。
