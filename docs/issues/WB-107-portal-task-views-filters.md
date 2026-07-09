---
id: WB-107
title: BuddyWebMgr 门户任务 —— 列表视图 + 甘特/时间线视图 + 筛选/排序
severity: P2
area: frontend
status: fixed
origin: WB-103 分片 P2（门户 UI 期二片）
files:
  - hub/web/console.html
created: 2026-07-09
---

## 问题

WB-106 把门户任务做成专业看板 + 详情抽屉，但只有看板一种视图、无筛选。补 **列表 / 甘特** 双视图 + 筛选/排序，凑齐「完整专业 PM」的视图层。见 epic [WB-103](WB-103-professional-pm-epic.md)。

## 建议修法

`hub/web/console.html` 任务区（在 WB-106 的 `pmRender*` 基础上扩展，续用 `pm-` 前缀 + 内联样式）：
- **视图切换器**：看板 / 列表 / 甘特（跨刷新保持 `PM_VIEW`）。
- **筛选行**：搜索标题 + 状态/优先级/负责人/里程碑 下拉 + 排序（默认/优先级/截止），作用于全部视图（`PM_FILTER`/`PM_SORT`，`pmFiltered()`）。
- **列表视图**：表格（标题/状态/优先级/负责人/截止/里程碑），行点开抽屉。
- **甘特视图**：按 start_date→due_date 画横条（相对日期刻度），无排期任务提示；条点开抽屉。
- 搜索用局部重渲染 `#pm-view`（不重建搜索框，避免失焦）。

**并发防撞**：同 WB-106 —— 全 pm- 前缀 + 内联样式（不碰 `<style>`）、只动任务区、提交按 hunk 只暂存我的块。

## 验证

隔离 Hub + CDP：三视图切换正确；筛选（按优先级/负责人/里程碑/搜索）实时生效；甘特按日期画条；列表可点开抽屉；无 JS 报错、无横向溢出（表格 `overflow-x`）。

## 处理记录（2026-07-09）
- 改动：`hub/web/console.html` 任务区——加 `PM_VIEW/PM_SORT/PM_FILTER` 状态（跨刷新保持）；`loadWorkItems` 改调 `pmRender()`；`pmRenderBoard` 拆为 `pmRender`（外壳：里程碑条+视图切换器 看板/列表/甘特+筛选行 搜索/状态/优先级/负责人/里程碑/排序+快速新建）/`pmRenderView`（局部渲染 #pm-view，搜索不失焦）/`pmFiltered`（筛选+排序）/`pmViewBoard`/`pmViewList`（表格 overflow-x）/`pmViewGantt`（start→due 相对横条+日期刻度，按优先级着色，无排期排除）。续用 pm- 前缀 + 内联样式（不碰 `<style>`）。
- 验证：`node --check` 语法过；隔离 Hub(:8155)+CDP：board 4/4→列表(4行6列)→甘特(3带排期任务画条,无排期排除)→筛选紧急 1/4(看板剩1卡)；**JS ERRORS: NONE**；甘特截图三条橙/红/绿按日期定位正确、暗色一致、无横向溢出。
- commit：同 WB-106，console.html 共享，按 hunk 只暂存我的块（`git apply --cached`）后提交。
