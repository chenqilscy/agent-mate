---
id: WB-016
title: 可点击 <div> 无键盘可达 / 焦点
severity: P2
area: ui
status: open
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
