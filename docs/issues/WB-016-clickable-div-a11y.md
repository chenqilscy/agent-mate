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

## 复发审查（2026-07-21）
- Ant Design 迁移后的全量静态复核仍检出 123 行 `div/span/li + onClick`，其中仅约 17 行使用 `activate()`；专家分类、项目面包屑、菜单项、卡片和删除图标等仍不可通过键盘触达。
- App 仍有原生 `confirm/prompt`，Console 高级 JSON 的启用 Switch 缺少可访问名称，专业组件迁移后的焦点和对话框体验尚未闭环。

## 处理记录（2026-07-21）
- 改动：新增兼容既有点击路径的 `clickable` 键盘语义，覆盖 App 中所有 `div/span/li/b/svg/ProCard` 等非原生点击控件；禁用态不进入 Tab 序列；高级 JSON Switch 补目录身份名称。原生 `confirm/prompt` 全部迁为 Ant App Modal，并为保存视图提供 Ant Input 校验。
- 验证：AST 全量扫描 `ACTIONABLE_MISSING=0`；`window.confirm/prompt/alert` 搜索为空；浏览器用 Tab 聚焦 SkillHub 分类并以 Enter 成功切换，焦点环、`role=button`、`tabIndex=0` 均存在。
- 提交：本次 WB-016/WB-252/WB-253/WB-254/WB-256 UI 审查修复提交。
