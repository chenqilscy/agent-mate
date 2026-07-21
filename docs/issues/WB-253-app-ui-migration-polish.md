---
id: WB-253
title: App 组件迁移后残留暗色、布局、侧栏与分类细节问题
severity: P1
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/styles/app.css:1534
  - src/styles/tokens.css:16
  - src/views/ProjectsView.tsx:34
  - src/components/layout/Sidebar.tsx:251
  - src/views/ExpertsView.tsx:364
created: 2026-07-21
---

## 问题
- 自动化页暗色选中 Tab 使用始终为白色的 `--card`，实测白底浅字。
- 项目页搜索框固定在内容最右侧，而项目列表固定最大宽度 400px，操作与对象视觉脱节。
- 侧栏默认同时展开任务、空间、自动化，并完整渲染 67 个普通任务；505px 可视区承载约 2937px 内容。
- SkillHub 分类直接显示英文 slug，与中文界面不一致。

## 触发场景
分别打开暗色 `/automations`、桌面 `/projects`、任务历史较多的任意页面以及 `/skills` 的 SkillHub 页签。

## 影响
P1：关键入口的可读性、信息关系和导航效率明显低于专业控制台基线。

## 建议修法
使用暗色语义表面 token；让项目搜索与项目列表共享内容宽度；普通任务只展示最近条目并提供“查看全部”；默认仅展开任务组；为已知 SkillHub 分类提供中文展示映射并保留原 slug 作为筛选值。

## 验证
- 自动化选中 Tab 明暗主题均清晰。
- 1440px 与 860px 项目页搜索和项目卡片对齐且无溢出。
- 侧栏默认首屏可看到其他分组入口，仍可搜索全部会话。
- SkillHub 分类显示中文，筛选结果不变。

## 处理记录（2026-07-21）
- 改动：暗色自动化选中 Tab 改用主题表面 token；项目搜索行与列表统一 640px 内容宽；侧栏默认仅展开任务并只显示最近 12 条，可显式展开全部；SkillHub 与推荐分类增加中文展示映射，筛选值仍使用原 slug。
- 验证：明暗主题选中 Tab 分别为白底深字与 `rgb(42,48,54)` 深底浅字；1440px/860px 项目搜索和列表左右边界完全一致；侧栏首屏可见空间与自动化入口；SkillHub 11 类均显示中文且 Enter 键可筛选。
- 提交：本次 WB-016/WB-252/WB-253/WB-254/WB-256 UI 审查修复提交。
