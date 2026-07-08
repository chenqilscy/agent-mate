---
id: WB-088
title: 多助理 S2 —— 前端多助理管理 UI（列表/新建/设置/对话/渠道）
severity: P1
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/AssistantView.tsx
  - src/stores/assistantStore.ts
  - src/lib/api.ts
  - src/components/channel/
created: 2026-07-08
---

## 问题

WB-087 后端已就绪（`/api/assistants*`）。把「助理」页从单助理面板（WB-077/085）重构为
**主从多助理管理视图**：左侧助理列表 + 新建，右侧选中助理的 对话 / 设置 / 渠道 三 tab。
（合并 epic 的 S2 + S3 前端，避免中间断档：一次给出完整可配置 UI。）

## 建议修法

- `lib/api.ts`：Assistant / AssistantChannel / ChannelType 类型 + 全套方法（list/get/create/update/delete/
  say + channel add/update/delete/unbind + channelTypes）。
- `stores/assistantStore.ts`：assistants 列表 + 选中态 + CRUD 动作（走 api），供视图与子组件。
- `views/AssistantView.tsx`：主从布局——
  - 左：助理列表（头像/名字/状态点）+「＋ 新建助理」。
  - 右 · 对话：真实 transcript（复用 MessageList + WB-085 搜索/分享/历史）+ Composer（→ say），轮询刷新。
  - 右 · 设置：名字/头像/指令/模型/权限(执行·计划·问答)/工作空间(默认·项目·专属) + 专家·技能·连接器
    （复用 PickerOverlay）→ PATCH。
  - 右 · 渠道：渠道列表（类型/状态/绑定）+「＋ 新增渠道」（类型选择：Telegram 可用、其它「敬请期待」占位）
    + Telegram 表单（token write-only / chat_id 白名单 / 启停）+ 每渠道 解绑/删除。
- 复用 `.np-*` / `.fic` / `PickerOverlay` / `ModelPicker` / `Popover`；主从布局少量 scoped CSS 用既有 token。

## 验证

- `npx tsc --noEmit` / `npx vite build` 通过。
- 建第二个助理、切换、改设置(指令/模型/权限/工作空间/loadout)保存生效；渠道新增/启停/解绑；对话可发。
- 明暗双主题过一遍。真机多 bot 路由留 S3/WB-089。

## 处理记录（2026-07-08）

- 改动：
  - `lib/api.ts`：Assistant / AssistantChannel / ChannelType / AssistantInput / ChannelInput 类型 +
    全套方法（list/get/create/update/delete/say + channel add/update/delete/unbind + channelTypes）。
  - `views/AssistantView.tsx`：全量重写为主从视图——左侧助理列表(头像/名字/状态点)+「＋新建」，右侧
    对话/设置/渠道 三 tab + 删除；4s 轮询列表状态点与选中 transcript。
  - 新 `components/channel/AssistantChat.tsx`（对话面板，复用 MessageList/ChatSearch/exportChat/Popover，
    含搜索/分享/历史）、`AssistantSettingsForm.tsx`（名字/头像/指令/模型/权限段/工作空间段+项目选择/
    专家·技能·连接器 复用 PickerOverlay）、`AssistantChannels.tsx`（渠道列表+类型菜单(Telegram 可用、
    其它「敬请期待」)+Telegram 表单 token(write-only)/白名单/启停 + 每渠道 停用/编辑/解绑/删除）。
  - 删除 WB-077 的 `AssistantSettingsModal.tsx`（被内联设置替代）。`styles/app.css` 加 `.asst-*` 主从布局
    （全用带暗色覆盖的语义 token）。
- 验证：`tsc`/`vite build` 通过。真机跑通新 UI 依赖的整套端点：建第二个助理(小研,mode=ask)、列出(小助,小研)、
  PATCH 设置(model+专家+workspace=dedicated)、加 Telegram 渠道、`/say` 按该助理人格+mode 回「我叫小研…」、
  无 token 泄漏、删除回到 1 个。未跑：浏览器明暗实时截图（Playwright profile 被占）；CSS 全用 token 无硬编码风险色。
- commit：（尚未提交）
