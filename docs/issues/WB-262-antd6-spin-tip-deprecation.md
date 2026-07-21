---
id: WB-262
title: App 与 Console 仍使用 Ant Design 6 已弃用的 Spin tip 属性
severity: P2
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/views/KnowledgeView.tsx:198
  - src/components/settings/SettingsModal.tsx:424
  - console/src/App.tsx:106
created: 2026-07-21
---

## 问题

App 与 Console 多处 `Spin` 仍传入 Ant Design 6 已弃用的 `tip` 属性，浏览器在实际页面输出 `[antd: Spin] tip is deprecated` 警告。Ant Design 6 应使用 `description`。

## 触发场景

打开 AgentMate App 首页或进入任一使用加载态的页面，开发者控制台会输出弃用警告；Console 的启动和懒加载占位也使用同一旧属性。

## 影响

P2：当前功能仍可用，但会污染浏览器诊断输出，并可能在后续 Ant Design 升级时失效。

## 建议修法

将 App 与 Console 中所有 `Spin` 的 `tip` 属性迁移为 `description`，保留原文案与布局类名。

## 验证

- 源码中不再存在 `<Spin ... tip=`。
- App/Console TypeScript 检查与生产构建通过。
- 浏览器加载 App 和 Console 后不再出现 Spin 弃用警告。

## 处理记录（2026-07-21）

- 改动：将 App 与 Console 共 12 处 `Spin.tip` 全部迁移为 Ant Design 6 支持的 `Spin.description`，保留加载文案与布局类名。
- 验证：源码门禁确认 `<Spin ... tip=` 为 0；App/Console TypeScript 检查及 `pnpm build` 全部通过，Console 正式静态产物已重新生成。
- commit：本提交
