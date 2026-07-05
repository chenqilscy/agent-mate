---
id: WB-016
title: 可点击 <div> 无键盘可达 / 焦点
severity: P2
area: ui
status: fixed
origin: 🏚 迁移遗留
files:
  - src/views/ChatView.tsx:71
  - src/components/layout/Sidebar.tsx
  - src/components/composer/PlusMenu.tsx
created: 2026-07-06
---

## 问题
头部 `.fic`（搜索/分享/历史/产物面板）以及侧栏 `.nav-item`/`.sb-task`/`.sb-ico`、`.pop-item`、`.more-item`、`.pf-row` 等大量交互元素是 `<div onClick>`，虽多数带 `aria-label`，但无 `role="button"`/`tabIndex`，无法获得焦点，全局 `:focus-visible`（`tokens.css:104`）永不触发。

（Composer 内的按钮用的是 `<button>`，是好的；问题集中在这些 div。）

## 触发场景
纯键盘 / 读屏用户无法触达这些控件。

## 影响
可访问性缺陷。属原型逐字迁移遗留，范围广。

## 建议修法
为交互 div 补 `role="button"` + `tabIndex={0}` + Enter/Space 处理，或逐步迁为 `<button>`。可先覆盖高频入口（头部、侧栏、＋菜单）。

## 验证
Tab 能聚焦这些控件并显示 focus ring，Enter/Space 可激活。

## 处理记录（2026-07-06）
- 改动：新增 `activate()` helper（role=button/tabIndex/Enter·Space）；应用到高频入口：ChatView 头部 .fic、Sidebar 图标/nav-item/分区/任务行/展开箭头/通知发现、PlusMenu 各项与模式开关（开关用 role=switch + aria-checked）。（src/lib/a11y.ts（新增）, src/views/ChatView.tsx, src/components/layout/Sidebar.tsx, src/components/composer/PlusMenu.tsx）
- 验证：`tsc`/`vite build` 通过；这些控件现可 Tab 聚焦、显示 focus ring、Enter/Space 激活。范围收敛在高频入口，其余 div 后续逐步迁移。
