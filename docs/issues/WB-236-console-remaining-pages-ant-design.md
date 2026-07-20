---
id: WB-236
title: AgentMate Console 其余 legacy 页面尚未迁移到统一组件体系
severity: P1
area: frontend
status: open
origin: 🏚 迁移遗留
files:
  - server/web/console.html:347
  - server/main.py:87
created: 2026-07-21
---

## 问题

WB-234 已建立 React + Ant Design 6 + Pro Components 构建边界，并完成技能目录管理样板页；
概览、项目、组织、专家、连接器、知识库、用户、通知和高级 JSON 仍由约 200 KB 的
`server/web/console.html` 手写实现。新旧页面在迁移期功能连续，但视觉、反馈与维护方式尚未全站统一。

## 触发场景

从新 `/catalog/skills` 侧栏进入任一其他功能，或点击目录预览/推荐位管理进入 `/legacy/*`，
页面会切回旧 Console 组件体系。

## 影响

P1：不阻断现有功能，但 Console 的整体专业化尚未完成；继续给 legacy 页面叠加功能会扩大最终迁移成本。

## 建议修法

- 以 WB-234 的主题、ProLayout、API client、表格/Drawer/反馈范式为基座，按“目录类 → 用户组织 → 项目工作台”迁移。
- 每迁移一个稳定路由就让 Server 切到 React History 入口；保留同源 API、权限和 local-first 边界。
- 把目录预览和推荐位管理迁入 SkillsPage 后再删除技能页的 `/legacy` 回退；全部迁完才移除旧单文件。
- 对大型路由使用动态 import 拆包，降低当前管理页首包体积。

## 验证

- 所有 Console 稳定 URL 均由 React 入口直达、刷新和前进/后退正常，功能与旧页面一致。
- 平台管理员/普通成员权限正确；加载、空、错误、确认与成功反馈统一。
- 明暗主题、1920/1280/860px 浏览器验收通过；关键 CRUD 调用真实 Server API。
- 旧 `console.html` 和 `/legacy/*` 删除后无悬挂链接，构建与回归门禁全绿。
