---
id: WB-261
title: AgentMate App 与 Console 字体体系和基础排版密度不一致
severity: P1
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/components/ui/AppThemeProvider.tsx:15
  - src/styles/tokens.css:20
  - console/src/App.tsx:116
  - console/src/styles.css:7
created: 2026-07-21
---

## 问题

AgentMate App 与 Console 虽然都已迁移至 Ant Design 6.5.1 和 Pro Components 3.1.14-2，但两端使用不同字体栈和排版算法。App 的 Ant 根节点为 14px/22px，Console 因全局启用 `compactAlgorithm` 变为 12px/20px；菜单字重也分别为 600 与 400。App 的 body 与 Ant Theme 还各自维护一套字体栈。

## 触发场景

在同一台 Windows 设备上分别打开 AgentMate App 与 `http://127.0.0.1:8100`，对比导航、按钮与正文，可明显看到 Console 字号更小、字重更轻、行高更紧，形成两套品牌视觉。

## 影响

P1：两端属于同一产品体系，基础字体节奏不一致会持续放大页面迁移后的割裂感，并让 Console 在高分辨率屏幕上可读性偏低。

## 建议修法

- 建立两端共享的字体族、基础字号和行高令牌。
- App 的 body 与 Ant ConfigProvider 使用同一字体栈，删除未实际加载的 Inter 优先项。
- Console 移除会把基础字号降至 12px 的全局 `compactAlgorithm`；需要紧凑感时使用组件尺寸与现有页面间距控制。
- 在明暗主题下检查两端导航、按钮、正文和标题的实际计算样式。

## 验证

- 两端 `.ant-app` 的计算样式均为统一字体栈、14px 基础字号和 22px 行高。
- 两端菜单与按钮的基础字重统一，中文与英文混排无明显跳变。
- App/Console TypeScript 检查与生产构建通过。
- 明暗主题及 `127.0.0.1:8100` 实际站点浏览器检查通过。

## 处理记录（2026-07-21）

- 改动：新增共享字体 CSS/TS 令牌；App 与 Console 的 ConfigProvider、body、菜单和按钮统一字体栈、14px/22px 基础排版及 600 控件字重；Console 以 `componentSize="small"` 保留紧凑控件，移除会压缩正文的全局 `compactAlgorithm`。
- 验证：App/Console TypeScript 检查与 `pnpm build` 通过；浏览器在两端明暗主题下确认 body、`.ant-app`、PageContainer 均为同一字体栈与 14px/22px，菜单/按钮均为 14px/600，1280×720 无横向溢出；主题已恢复为深色。
- commit：本提交
