---
id: WB-355
title: 项目健康面板绕过 Ant 按钮契约导致完整回归失败
severity: P0
area: frontend
status: in-progress
origin: 🆕 近期改动
files:
  - src/views/ProjectsView.tsx:152
  - src/styles/app.css:1766
created: 2026-08-03
---

## 问题

项目健康面板新增原生 `button`，并用后代选择器隐式声明无边框样式，绕过统一 `WbButton` 与显式 borderless 契约。

## 触发场景

运行完整 Backend 回归，Ant 迁移的原生控件和无边框 hover 两项契约测试稳定失败。

## 影响

P0。当前发布门禁为红，且按钮 hover/主题行为可能重新漂移。

## 建议修法

使用 `WbButton`，增加产品级显式 class，并把该 class 纳入既有无边框视觉契约；保持现有布局和视觉。

## 验证

- 两项失败测试通过；
- `npx tsc --noEmit` 与 App 生产构建通过；
- 明暗主题下项目健康按钮布局、hover 和键盘操作正常。
