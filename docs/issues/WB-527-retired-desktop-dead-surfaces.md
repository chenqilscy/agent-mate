---
id: WB-527
title: Desktop 业务面退役后遗留不可达 View 与陈旧契约
severity: P2
area: frontend
status: in-progress
origin: 🏚 迁移遗留
files:
  - src/App.tsx:20
  - src/views/AssistantView.tsx:23
  - src/views/ProjectHomeView.tsx:302
  - src/views/MyFilesView.tsx:141
created: 2026-08-12
---

## 问题

WB-517～521 已把业务入口迁往 Server，但 `AssistantView`、`InspireView`、`KdocsView`、`MyFilesView`、`ProjectHomeView`、`ProjectsView` 及其专用组件仍留在源码中且无入口；部分回归继续验证旧业务结构。

## 触发场景

维护者搜索项目/文件/助理功能 → 修改不可达代码；全量回归又对删除后的旧 View 失败，无法区分真实产品回退。

## 影响

P2：扩大维护面、构建与审查成本，诱发在已经退役的 App 业务面继续开发。

## 建议修法

按引用图删除确定不可达的 View、Store/API 与仅供这些 View 使用的组件；对仍由现有 Run 工件面使用的文件组件保留；同步重写边界契约测试。

## 验证

- 静态引用检查无悬空 import。
- `pnpm build` 和全量回归通过。
- 旧 URL 回退到 Home/Server 交接，现有 Run 工件与本机知识源仍可用。

## 处理记录（2026-08-12）

- 已删除无入口且无并行改动的 `AssistantView`、`InspireView`、`KdocsView`、`ProjectHomeView`、`AssistantChat`、`ProjectTaskCenter`、`ServerCommentsPanel`，并删除/重写只验证这些退役页面的回归契约与死 CSS。
- 已验证 App/Console 生产构建、469 条 Desktop/Local Agent 回归和真实浏览器 Home/设置页面通过；旧 `/new` 路由继续拒绝，本机知识源与既有 Run 页面仍可构建。
- 尚未删除 `MyFilesView`、`ProjectsView`、`ProjectWork`、`AssetsManager`：当前共享工作区中它们承载 WB-437/WB-494/WB-495 的未提交改动，直接删除会覆盖其他会话成果。它们当前未被 `App.tsx` 引用、不会进入产品路由；待并行改动完成后再做物理删除和关联 API/Store 收口。
