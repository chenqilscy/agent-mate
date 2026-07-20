---
id: WB-234
title: AgentMate Console 技能管理的单文件手写 UI 难以形成专业一致的管理体验
severity: P1
area: frontend
status: fixed
origin: 既有实现
files:
  - server/web/console.html:7
  - server/web/console.html:1999
  - server/main.py:19
created: 2026-07-21
---

## 问题

AgentMate Console 把全站样式、路由、鉴权、目录 CRUD 与弹窗编辑器集中在约 200 KB 的
`server/web/console.html` 单文件中。基础按钮、表单、表格、菜单、反馈与响应式行为均为手写，
不同阶段追加的局部 class 和交互逐渐产生视觉密度、层级、状态表达及键盘可用性不一致。

技能目录管理尤其明显：搜索筛选纵向占满内容区，每条技能以无语义长卡片平铺，名称、slug、
分类、版本、排序、文件数和状态挤在同一行 pill 中，主要动作重复铺开，宽屏又留下大量空白。
根因不是单个 CSS 参数，而是 Console 没有可复用的专业管理台组件体系和可维护的前端构建边界。

## 触发场景

平台管理员登录 Console → 进入 `/catalog/skills` → 切换“目录管理”。在 1920px 宽屏下，
筛选器整行堆叠、列表扫描层级弱、行操作重复且内容宽度利用率低；条目增长或切到窄屏后，
手写控件还需要逐处补响应式、加载态、空态、错误态和无障碍行为。

## 影响

P1：Console 是 Server 的正式管理入口，视觉与交互专业度直接影响产品可信度；继续在单文件中
追加手写组件还会放大维护成本和回归风险，阻碍后续项目、组织和目录运营能力扩展。

## 建议修法

- 新建独立 React 19 + TypeScript + Vite Console 前端，使用 MIT 许可的 Ant Design 6 与
  Pro Components；通过主题 token 映射 AgentMate 品牌色，支持明暗与紧凑模式。
- 保持 FastAPI 与 `/api/*` 契约不变，生产构建由 Server 同源托管；迁移期间按路由让新旧页面并存。
- 第一阶段先迁移登录态、专业管理台外壳和 `/catalog/skills`：目录管理使用 ProTable，搜索筛选
  进入工具栏，编辑使用 Drawer/Modal，状态切换、归档、排序和文件维护继续调用真实 Server API。
- 未迁移页面仍链接旧 Console，待逐页验收后再移除 `console.html`。

## 验证

- 新 Console 可在无 token 时登录，已有 `agentmate.console.token` 可直接恢复账号；普通用户不能访问管理页。
- `/catalog/skills` 真实加载、搜索、分类/状态筛选、新增、编辑、启停、归档、排序与文件维护均可用。
- FastAPI 同源提供入口与静态资源，未知 `/api/*` 仍返回 404，不被 History 回退伪装成 HTML。
- `npx tsc --noEmit`、Console 独立构建、Server 测试通过；浏览器实测明暗主题与 1920/1280/窄屏。

## 处理记录（2026-07-21）

- 改动：新增 `console/` React 19 + TypeScript 前端与独立 Vite 构建，引入 Ant Design 6.5.1、
  明确支持 antd 6 的 Pro Components 3.1.14-2；`/catalog/skills` 使用 ProLayout、PageContainer、
  ProTable 和 Drawer，完成登录恢复、搜索筛选、新增/编辑、工具绑定、文件编辑、启停、归档与排序。
  Server 同源托管构建资源，未迁移页面通过 `/legacy/*` 保持可用。
- 验证：`pnpm build:console` 通过；Server 22/22、backend regression 35/35 通过，`server/main.py`
  py_compile 通过。隔离 Server 真 API 浏览器验收完成注册、6 条种子技能加载、`excel` 搜索、创建
  `wb234-ui-smoke`（含 `references/ui-smoke.md`）、启停往返、无改动关闭、旧页面回退、明暗主题、
  860px 无整页横向溢出，浏览器错误日志为空。本机 Server :8100 已硬重启，健康检查与构建资源均 200。
- commit：本提交（WB-234）。
