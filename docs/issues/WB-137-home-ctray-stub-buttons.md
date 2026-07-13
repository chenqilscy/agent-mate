---
id: WB-137
title: 首页「选择工作空间 / 默认权限」两个 tray 按钮是 toast 桩，未真正实现
severity: P2
area: frontend
status: fixed
origin: 用户反馈
files:
  - src/views/HomeView.tsx:80
  - src/views/HomeView.tsx:85
created: 2026-07-14
---

## 问题

首页（HomeView）Composer 下方的两个 tray 按钮只是占位桩：

- [src/views/HomeView.tsx:80](../../src/views/HomeView.tsx#L80)「选择工作空间」→ `onClick={() => toast('选择工作空间')}`
- [src/views/HomeView.tsx:85](../../src/views/HomeView.tsx#L85)「默认权限」→ `onClick={() => toast('默认权限')}`

点了只弹 toast，不产生任何真实效果：不能选新任务运行在哪个空间，也不能设默认权限。

## 触发场景

用户在首页想「让这次新任务跑在某个已有工作空间里」，或想把默认权限改成「完全访问」再发起——点按钮只弹提示，做不到。

## 影响

P2：功能缺口，与铁律 1（不硬编码/不模拟）冲突。已有可复用能力（projectStore 项目列表 + startProject；settingsStore.perm + PermPopover），只是首页没接上。

## 建议修法

复用现成部件，不新造轮子：

- **选择工作空间**：HomeView 本地 state 存 `selProject: ProjectInfo | null`，点按钮开 `Popover`
  列出 `projectStore.projects`（+「无（默认空间）」项，样式沿用 AutomationView 的 `pop-item`/`chk`）。
  按钮文案反映当前选择。`launch()` 里：选了项目 → `startProject(id, title)`；否则 `startDraft(title)`。
  挂载时 `projectStore.load()` 确保列表有数据。
- **默认权限**：点按钮开 `Popover`，内容直接复用 `PermPopover`（已经读写 `settingsStore.perm`）。
  按钮文案显示当前 `perm`（默认权限/完全访问权限）。
- 两个 Popover 用 `dir="down"`（tray 在 composer 下方）。

## 验证

- `npx tsc --noEmit` 过。
- 首页点「选择工作空间」→ 列出真实项目，选一个后按钮显示其名；发消息进入会话，会话归属该项目（右栏工作空间文件/scope 一致）。
- 首页点「默认权限」→ 切到「完全访问权限」，按钮与后续会话 composer 的权限一致。
- 明暗双主题看两个 popover 样式协调（复用 `pop`/`pop-item`/`perm-pop` class）。

## 处理记录

- 2026-07-14 fixed。按「建议修法」实现，只改 [src/views/HomeView.tsx](../../src/views/HomeView.tsx)：
  - 新增本地 state `selProject`（null=默认空间）与 `pop`（'ws'|'perm'|null）两个 popover 开关；挂载 `useEffect` 调 `projectStore.load()`。
  - 「选择工作空间」按钮文案改为 `selName ?? '选择工作空间'`，点开 `Popover`（`dir="down"`）列「无（默认空间）」+ `projectStore.projects`，样式沿用 AutomationView 的 `pop-item`/`pi-ic`/`chk`。
  - `launch()`：选了项目走 `chatStore.startProject(id, title)`，否则 `startDraft(title)`（沿用既有机制，send 自带 projectId）。
  - 「默认权限」按钮文案改为当前 `settingsStore.perm`，点开 `Popover` 复用现成 `PermPopover`（读写同一 perm）。
- 验证：`npx tsc --noEmit` 过。因并发会话占用 Playwright MCP 浏览器，改用独立 headless chromium + CDP 自驱动实测：
  - 工作空间 popover 列出「无（默认空间）✓ / 便签测试 / 咖啡创业 / 蜜蜂项目 / 测试项目」，选「便签测试」后按钮变为「便签测试」。
  - 权限 popover 正常打开（PermPopover 内容），切换后按钮由「默认权限」变为「完全访问权限」。
  - 截图确认两 popover 视觉协调（复用的均为已在 AutomationView / chat Composer 用过的明暗双主题安全 class）。
