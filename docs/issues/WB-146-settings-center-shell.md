---
id: WB-146
title: 统一「设置中心」弹窗 —— 双栏外壳 + 迁移已有标签（模型/助理设置/外观·个性化），其余标签诚实占位
severity: P1
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/components/settings/SettingsModal.tsx
  - src/stores/uiStore.ts
  - src/components/layout/Sidebar.tsx
created: 2026-07-14
---

## 问题

参照高保真截图，WorkBuddy 需要一套**统一的多标签「设置中心」弹窗**：左侧标签导航（账户管理 /
系统设置 / 智能体设置 / 快捷键 / 记忆 / 模型 / 助理设置 / 个性化 / 数据管理 / 安全中心 /
帮助与反馈）+ 右侧内容区；入口从左下角账号浮层的「设置」进入。

现状：**没有**统一容器。设置散落在三处——`ModelConfigModal`（模型，全栈已成熟）、
`AssistantSettingsForm`（助理设置）、Sidebar 账号浮层（仅浅/深色切换 + 帮助反馈 toast 桩）。
11 个标签里只有「模型」「助理设置」真落地，个性化仅外观切换，其余 7 个几乎全无、多为 `toast()` 桩。

## 触发场景

用户点左下角账号头像 → 浮层里没有「设置」入口；截图那套语言/字号/记忆/安全/数据管理等能力无处可达。

## 影响

P1：这是产品设置面的骨架，缺它则截图里近半功能不可达；且散落的入口（模型在「更多」菜单、外观在账号浮层）
体验割裂。首期只搭骨架 + 迁移已有，风险可控。

## 建议修法（首期 = 外壳 + 迁移已有）

1. **外壳** `src/components/settings/SettingsModal.tsx`：套现有 `.np-overlay`/`.np-modal`
   （复用 `ModelConfigModal` 的类，token 化天然暗色，符合铁律#2/#3）。左侧 `nav` 列出 11 标签，
   右侧按 `activeTab` 切 panel。
2. **状态**：`uiStore` 加 `settingsOpen` + `settingsTab`（照抄现有 `modelConfigOpen` 写法）。
3. **入口**：账号浮层（Sidebar.tsx:432 附近）加「设置」项 → `setSettingsOpen(true,'system')`。
4. **迁移已有为 panel**：
   - 模型 → 直接嵌入现成 `ModelConfigModal` 的内容（抽成可内嵌形态）。
   - 助理设置 → 复用 `AssistantSettingsForm`（或跳转助理页，首期可先跳转/嵌入）。
   - 个性化 → 外观浅/深色切换（从账号浮层迁来）+ 预留风格语调/自定指令 UI。
5. **其余 7 标签**（系统设置/快捷键/记忆/数据管理/安全中心/账户管理/帮助与反馈）：
   按截图做 UI，但**未接后端的数据/开关诚实标注「即将上线」**，不造假数据（铁律#1）。
   各自的真后端（记忆 DB、安全审计、系统设置持久化等）拆到后续 issue。

## 验证

- `npx tsc --noEmit` 过；`npx vite build` 需要时过。
- Playwright 实测：账号浮层点「设置」能开弹窗；11 标签可切换；模型/助理设置/外观三个 panel 真可用；
  占位标签明确显示「即将上线」不伪造数据。
- **明暗双主题**都看一遍（铁律#3）。

## 处理记录（2026-07-14）

- 改动：
  - 新增 `src/components/settings/SettingsModal.tsx`——双栏外壳（左 11 标签 nav + 右 panel），套 `.np-overlay/.np-modal`，新增 `set-` 前缀样式。
    - 账户管理：真数据（`me` 的用户名/套餐/角色/凭据状态 + 登录/退出）。
    - 模型：内嵌 `ModelConfigModal`（下述 `embedded` 模式），复用成熟全栈。
    - 个性化：外观浅/深切换（`seg2`，从账号浮层迁来）+ 风格语调/自定指令「即将上线」占位。
    - 助理设置：跳转「助理」页。
    - 系统设置/智能体设置/快捷键/记忆/数据管理/安全中心：`Soon` 占位组件，诚实标「即将上线」+ 列出规划项，不造假数据（铁律#1）。
    - 帮助与反馈：入口按钮（反馈渠道/帮助文档「即将上线」toast）。
  - `src/components/composer/ModelConfigModal.tsx`：加 `embedded?` prop——true 时只渲染 `np-body` 内容（去掉自带 overlay/标题/底栏），供设置中心内嵌；默认行为不变。
  - `src/stores/uiStore.ts`：加 `settingsOpen`/`settingsTab` + `setSettingsOpen(open,tab?)`/`setSettingsTab`，导出 `SettingsTab` 类型。
  - `src/components/layout/Sidebar.tsx`：账号浮层加「设置」行（→ `setSettingsOpen(true,'account')`）+ 渲染 `<SettingsModal>`。
  - `src/styles/app.css`：`set-` 前缀样式。**关键坑**：`--card` 不随主题翻转（恒白），暗色下 `.set-panel`/`.set-nav-item.active` 用 `var(--card)` 会白底白字（`.set-v` 隐形），照 np-modal 约定补 `body.dark .set-panel/.set-nav-item.active { background:#1F242A }`。
- 验证：`npx tsc --noEmit` 过、`npx vite build` 过；真后端 `:8000` 起（`me` 返回真数据、模型 tab 真拉到 DeepSeek/智谱厂商列表）；MCP 浏览器被并发会话占用，改用独立 headless chromium + CDP 自截图，**明暗双主题**各 6 tab 核对——修复前暗色账户面板「奇/体验版」发虚（白底白字），补 `body.dark` 覆盖后全部亮白清晰、active 高亮到位、`即将上线` 占位诚实。
- commit：未提交（用户未要求）。
- 后续：记忆/系统设置/安全中心/数据管理等标签的真后端（新 DB 表 + 路由）另拆 issue。
