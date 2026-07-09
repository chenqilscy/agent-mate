---
id: WB-106
title: BuddyWebMgr 门户任务专业化 —— 看板卡片富信息 + 任务详情抽屉 + 里程碑 + 子任务 + 活动流
severity: P1
area: frontend
status: fixed
origin: WB-103 分片 P1（门户 UI 期）
files:
  - hub/web/console.html
created: 2026-07-09
---

## 问题

门户 `loadWorkItems`（WB-081）只是极简 4 列看板（标题 + 状态 select + 删除），未消费 WB-104/105 的专业字段（优先级/负责人/截止/标签/里程碑/子任务/活动流）。要与 App（WB-108）对齐、把门户项目管理做专业。见 epic [WB-103](WB-103-professional-pm-epic.md)。

## 建议修法

`hub/web/console.html` 的 `projectDetail` 任务区（重写 `loadWorkItems` + 加 `pm-` 前缀助手）：
- **卡片富信息**：优先级色点、标签 chip、🚩 里程碑、📅 截止、👤 负责人、☑ 子任务数。
- **任务详情抽屉**（点卡开）：编辑 标题/描述/状态/优先级/负责人(项目成员下拉)/截止/标签/里程碑 + 子任务(增/勾/删) + 活动流(GET .../activity)。
- **里程碑条**：列表 + 就地新建（POST /milestones）。
- **快速新建** 任务。Viewer 只读。

**并发防撞硬约束**：并发会话正改同文件的目录/橱窗区 + `<style>` 块。故本片**全用内联样式**（不碰 `<style>`）、所有 id/class 用 **`pm-` 前缀**、只动 `loadWorkItems` 一段；提交时只 hunk-stage 我的块（`git apply --cached`），绝不整文件 `git add`。

## 验证

Hub 隔离实例(临时 DB) + CDP 实截（MCP 浏览器被并发占用）：登录→建项目/里程碑/带字段任务→看板卡片富信息正确→开抽屉编辑全字段保存→子任务增/勾→活动流有真实事件；无 JS 报错、无横向溢出、暗色（门户仅暗）正常。

## 备注
- 甘特/时间线视图 + 列表视图 + 筛选留 **WB-107**（更重、非核心）。

## 处理记录（2026-07-09）
- 改动：`hub/web/console.html` 重写 `loadWorkItems`（Promise.all 拉 work-items/milestones/members）+ 新增 `PM_PRIO`/`PM_CTX`/`pmMsName`/`pmCardHtml`/`pmRenderBoard`/`pmOpenTask`。卡片富信息（优先级色点/标签/🚩里程碑/📅截止/👤负责人/☑子任务数）；里程碑条（列表+就地新建）；任务详情抽屉（右侧 overlay，编辑 标题/描述/状态/优先级/负责人(成员下拉)/截止/里程碑/标签 + 子任务增·勾·删 + 活动流）。**全 pm- 前缀 + 内联样式**，不碰 `<style>`（避开并发会话 WB-100/101/102 gallery 改动区）。复用既有 WI_COLS 与 .card/.list-item/.pill/.field/.grid2 类。
- 验证：抽出 `<script>` `node --check` 语法过；隔离 Hub(:8155 临时 DB)+CDP 实测（MCP 浏览器被并发占用，法见 [[cdp-screenshot-when-mcp-browser-locked]]）：注入 token 登录→开项目→看板卡片富信息（探针=☑1·#后端#架构·🚩v1.0首发·📅07-20·👤pmuser）→开抽屉全字段正确（status doing/prio urgent/assignee pmuser/due 2026-07-20/ms 选中/labels 后端,架构）+子任务「选型调研」+活动流真实事件（priority high→urgent、created）→**JS ERRORS: NONE**；暗色渲染正常、无横向溢出。
- commit：console.html 与并发会话共享（其 WB-100 CSS 未提交），按 hunk **只暂存我的块**（`git apply --cached`）后提交。
- **甘特/时间线/列表视图/筛选** → WB-107（未做）。
