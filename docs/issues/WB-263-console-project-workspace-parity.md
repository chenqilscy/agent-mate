---
id: WB-263
title: Console React 迁移后项目工作台缩水并与 App 项目模型失配
severity: P1
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - console/src/pages/ProjectDetailPage.tsx:38
  - console/src/components/project/ProjectWorkspace.tsx:1
  - console/src/styles.css:100
  - docs/issues/WB-236-console-remaining-pages-ant-design.md:46
created: 2026-07-21
---

## 问题

WB-236 把 legacy Console 迁入 React + Ant Design 时，用单一任务表格替换了原有项目管理工作台。
当前 `console/src/pages/ProjectDetailPage.tsx` 只保留概览、任务、知识库、协作、配置五个标签；任务页仅有
`ProTable` 和编辑 Drawer。迁移前已经存在、且 WB-117 明确与 App 对齐的计划看板、WIP、泳道、保存视图、
批量操作、负载与甘特等 Server 权威项目能力没有等价迁回。

## 触发场景

打开同一个 Server 项目：AgentMate App 项目页提供计划/任务/负载/甘特等完整项目视图；Console 项目页只能
看到任务表格和管理卡片。用户无法在 Console 以相同项目模型进行计划、容量和时间排期管理。

## 影响

P1：Console 是 Server 权威项目协作入口。两端可以有不同外壳与执行边界，但同一批工作项在导航、状态、
负载和排期上的心智模型不一致，会让管理者误以为 Console 是另一套项目系统，并造成 WB-117 已完成能力回归。

## 建议修法

- 保留 Console 的 Ant Design 管理后台外壳，不复制 App 的本地执行输入框、会话正文或本地资产。
- 用 Server `work_items`、`milestones`、成员和协作 API 恢复统一项目工作台：概览、计划、任务、负载、甘特、
  知识库、协作、配置。
- 计划视图补齐状态看板、负责人/里程碑泳道、WIP 上限、保存视图、筛选、搜索和批量状态修改；所有写操作
  继续受 Viewer 门禁并落 Server 真数据。
- 任务详情与列表复用同一份数据加载/更新逻辑，负载和甘特从真实负责人、日期与工时字段派生。
- 复用 Console 现有 Ant Design token，覆盖明暗主题与窄屏，不引入 App 本地专属能力。

## 验证

- `npx tsc --noEmit`、`pnpm build:console` 通过。
- Console 项目页可切换概览/计划/任务/负载/甘特/知识库/协作/配置；刷新仍读取 Server 真数据。
- 看板拖拽或状态操作、批量更新、WIP、泳道和保存视图可用；Viewer 不出现写入口。
- 负载按成员聚合真实待办数与工时，甘特只展示带日期任务且时间跨度正确。
- 浏览器实测明暗双主题与窄屏，无横向不可达内容、无控制台错误。

## 处理记录（2026-07-21）

- 改动：新增共享 `ProjectWorkProvider` 与 Console 项目概览/计划/任务/负载/甘特视图；计划看板支持状态列、
  负责人/里程碑泳道、筛选搜索、WIP、保存视图、批量状态修改、拖放和统一任务抽屉。项目页扩展为
  概览/计划/任务/负载/甘特/知识库/协作/配置八个标签，保留 Ant Design 管理外壳且未引入本地执行入口。
- 验证：`npx tsc --noEmit`、`pnpm build:console` 通过；`pnpm test:regression` 86 项通过；本机 :8100
  真实账号/真实项目浏览器验收八标签、计划/任务/负载/甘特、WIP/保存视图弹窗、明暗主题和 800px 窄屏，
  页面整体横向溢出为 0、控制台 0 warning/error。
- commit：本提交（WB-263）。
