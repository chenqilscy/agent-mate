---
id: WB-256
title: App 与 Console 仍使用 Ant Design 6 已弃用的 List 组件
severity: P2
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/views/AssistantView.tsx:113
  - src/components/layout/Sidebar.tsx:258
  - console/src/pages/OverviewPage.tsx:52
created: 2026-07-21
---

## 问题
Ant Design 6.5.1 在开发模式中会对每个 `List` 实例输出弃用告警，并明确说明该组件将在下一主版本移除。App 与 Console 的导航、项目、自动化、知识库和管理详情仍大量依赖 `List` / `List.Item` / `List.Item.Meta`。

## 触发场景
打开助理、项目、自动化、知识库或 Console 概览等任一含列表的页面，浏览器控制台持续出现 `[antd: List] The List component is deprecated`。

## 影响
P2：当前页面仍可使用，但开发控制台被重复告警污染，且后续升级会直接失去列表组件；专业组件迁移未真正闭环。

## 建议修法
提供保持既有 WorkBuddy class 与 DOM 结构的语义列表基元，用原生 `ul/li`、空态和操作区替换已弃用的 Ant List；继续复用 Ant 的 Empty、Avatar、Button 等未弃用组件，并让可点击列表项默认具备 Enter/Space 键盘语义。

## 验证
- `src/` 与 `console/src/` 不再导入或渲染 Ant `List`。
- 助理、侧栏、自动化、知识库及 Console 概览/项目详情列表视觉不变。
- 浏览器重新加载相关页面后不再出现 `[antd: List]` 告警。
- App 与 Console 类型检查、生产构建通过。

## 处理记录（2026-07-21）
- 改动：新增 `CompatList` 语义列表基元，以 `ul/li`、Empty、Meta 与 actions 结构保留既有 Ant class 契约；App 与 Console 全部移除 Ant `List` 导入，可点击列表项内建 Enter/Space 语义。
- 验证：源码不再导入 Ant List；助理、侧栏及 Console 概览视觉复验无回归；全新浏览器会话分别加载 App 与 `127.0.0.1:8100`，`error/warning` 日志均为空；类型检查和完整生产构建通过。
- 提交：本次 WB-016/WB-252/WB-253/WB-254/WB-256 UI 审查修复提交。
