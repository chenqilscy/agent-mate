---
id: WB-237
title: AgentMate App 生产构建被现有 TypeScript 错误阻断
severity: P1
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/components/layout/Sidebar.tsx:211
  - src/components/project/ProjectWork.tsx:33
  - src/views/AutomationView.tsx:408
  - src/views/AutomationView.tsx:562
  - src/views/ExpertsView.tsx:223
created: 2026-07-21
---

## 问题

仓库级 `pnpm build` 在进入 WB-234 的独立 Console 构建前，被现有 AgentMate App TypeScript 错误阻断：
Sidebar 重复传入 `role`，ProjectWork/ExpertsView 存在未使用声明，AutomationView 的计时器调用参数与
`ModelOption.mult` 类型不匹配。`npx tsc --noEmit` 因根 tsconfig 仅含 project references 没有发现这些错误，
而 `tsc -b` 会稳定复现。

## 触发场景

在仓库根执行 `pnpm build` → `tsc -b` 退出码 2，Vite App 构建和后续 Console 构建均不执行。

## 影响

P1：生产构建门禁红灯，不能可靠生成完整 AgentMate App 发布产物；也会掩盖其他独立前端的构建结果。

## 建议修法

- 移除 Sidebar 重复 `role` 来源，保留实际可访问性语义。
- 清理确实未使用的声明，或恢复其真实用途，不能仅用禁用规则掩盖。
- 修正 AutomationView debounce/timeout 返回值类型与调用签名，并把 `mult` 补入权威模型类型或改用已有字段。
- 将日常类型门禁改为 `tsc -b --pretty false`，避免根 `tsc --noEmit` 假绿。

## 验证

- `pnpm build` 完整通过 App 的 `tsc -b`、Vite build 以及 `pnpm build:console`。
- Automation、专家页、侧栏和项目工作区浏览器回归无功能退化。

## 处理记录（2026-07-21）

- 改动：移除侧栏重复 `role`、清理未使用声明；自动化编辑器的间隔 state 不再遮蔽全局 `setInterval`，模型选择改为保存权威 `ModelOption.key` 并显示友好名称；统一回归脚本改用 `tsc -b --pretty false`。
- 验证：`pnpm build` 完整通过 App 与 Console 生产构建；`pnpm test:regression` 35 项通过且执行真实 `tsc -b`；浏览器实测侧栏、自动化模型选择、专家页、项目工作台及明暗主题，控制台 0 error。
- commit：本提交
