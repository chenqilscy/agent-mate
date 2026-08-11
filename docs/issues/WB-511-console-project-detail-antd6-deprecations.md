---
id: WB-511
title: Console 项目任务抽屉残留 Ant Design 6 弃用组件与属性
severity: P2
area: frontend
status: open
origin: 🆕 近期改动
files:
  - console/src/pages/ProjectDetailPage.tsx:943
  - console/src/pages/ProjectDetailPage.tsx:1327
  - console/src/components/project/ProjectWorkspace.tsx:1375
  - console/src/components/project/ProjectWorkspace.tsx:1467
  - console/src/components/project/WorkItemExecution.tsx:256
created: 2026-08-11
---

## 问题
WB-509 的真实浏览器复验打开项目任务详情抽屉后，控制台仍出现 Ant Design 6 的三类独立弃用告警：`Timeline.items.children` 应迁移到 `items.content`，`InputNumber.addonAfter` 应迁移到 `Space.Compact`，`List` 组件将在下一主版本移除。此前 WB-509 的问题边界只覆盖 `Card/Space/Drawer/Modal/Alert` 旧属性，现有静态防回归也未覆盖这些 API。

## 触发场景
平台管理员打开 Console 概览中的真实项目，进入含历史 Run 的任务详情抽屉；执行时间线、工时字段、评论与交付列表渲染时，浏览器控制台稳定输出上述弃用警告。

## 影响
任务详情是项目执行和验收的核心入口，持续告警会掩盖真实运行异常；相关 API 在后续 Ant Design 主版本删除后，时间线、工时输入或列表区域可能直接回归，按 P2 跟踪。

## 建议修法
按 Ant Design 6 当前 API 迁移所有项目详情路径：时间线项统一使用 `content`，工时输入用 `Space.Compact` 组合单位，列表改为受支持的 Table、Flex 或语义化 DOM；扩展 Console 源码契约测试并覆盖真实任务抽屉。

## 验证
Console 类型检查和生产构建通过；在有真实 Run 与交付的项目任务抽屉中覆盖内容、计划、更多信息和执行记录，浏览器控制台不再出现 `Timeline`、`InputNumber` 或 `List` 弃用警告，桌面与 600px 窄屏布局正常。
