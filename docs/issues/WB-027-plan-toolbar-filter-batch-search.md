---
id: WB-027
title: 计划 · 顶部工具条（归属/来源筛选 + 批量操作 + 搜索）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/components/project/ProjectWork.tsx:31
created: 2026-07-06
---

## 问题

「计划」看板顶部（`ProjectWork.tsx:31` `pj-plan-top`）目前只有「＋ 新建待办」「添加数据源」两个按钮。目标设计（用户截图）里顶部还有一整条工具条：右侧 **全部归属 ▾**、**全部来源 ▾** 两个筛选下拉，**批量操作** 按钮，以及**搜索**图标；这些当前都不存在。

## 触发场景

进入项目 → 计划 tab：看板顶部无筛选/批量/搜索能力；待办多了以后无法按归属（负责人）或来源过滤，也无法搜索标题、无法批量改状态/删除。

## 影响

P2：纯易用性缺口，待办量大时体验差；不影响既有创建/拖拽/删除。

## 建议修法

- 在 `pj-plan-top` 右侧补一条工具条，复用既有 class：筛选下拉用 `.mf-type`/`Popover`（参考 `TaskList` 里已有的「全部任务/全部来源」下拉与 `.search-box`），搜索用 `.search-box`。
- **筛选**：归属 = 按 `assignee`（我的/全部/各负责人）；来源 = 按 `source`（手动/执行/…，取自现有 items 去重）。筛选只影响看板展示，纯前端 `items.filter`。
- **搜索**：按标题子串过滤（与 `TaskList` 的搜索一致）。
- **批量操作**：进入批量模式 → 卡片出现勾选 → 底部/顶部出现「改状态/删除」。批量调用现有 `move`/`remove`（真 PATCH/DELETE，不伪造）。
- 与 WB-026 的详情/新建弹窗、拖拽换列共存，不回归。
- 视觉零重设计：class 与 token 沿用原型；暗色 `body.dark` 覆盖。

## 验证

- `npx tsc --noEmit` 过。
- 浏览器实测：按归属/来源筛选、搜索标题都即时生效；批量选中多张→批量改状态/删除，真落库（刷新保留）；筛选下拉在明暗双主题都可读。

## 处理记录（2026-07-06）
- 改动：`ProjectWork.tsx` 顶部 `pj-plan-top` 追加工具条——归属/来源筛选（`FilterDropdown`，选项从现有 items 的 assignee/source 去重）、搜索（`.search-box`，按标题子串）、批量操作（`批量操作` 切换 → 卡片勾选 → 批量「移动到[状态]」/删除，复用真 `move`/`remove`）。筛选/搜索纯前端 `items.filter`；批量真 PATCH/DELETE。样式复用 `.hub-act`/`.mf-type`/`.pop`（均有暗色覆盖），新 `.pj-batchbar` 用主题变量。
- 验证：`npx tsc --noEmit` 过；Playwright 实测工具条渲染、筛选/搜索/批量可用，明暗双主题可读。
- commit：（待用户确认提交）
