---
id: WB-119
title: App 端 PM 对齐 Manager 片3 —— 工作量视图（按负责人负载 tab）
severity: P2
area: frontend
status: fixed
origin: WB-117 App 对齐 epic 之片3；对齐 Manager pmViewWorkload
files:
  - src/components/project/ProjectWork.tsx
  - src/views/ProjectHomeView.tsx
created: 2026-07-10
---

## 背景

Manager 有「负载」视图（WB-115a pmViewWorkload）按负责人聚合工作量。App 项目工作台缺。本片把它搬到 App，作为项目页新 tab「负载」。含 WB-117 的工时汇总。

## 建议修法

- `ProjectWork.tsx` 加 `WorkloadView`：读 workItemStore 根任务，按 assignee(+未指派) 聚合，每人一卡（头像+名+总数 + 状态分布堆叠条(DOT 色) + 待办/进行/完成率 + 逾期红 + Σ预估/Σ投入工时）。复用 App token（`--card/--border/--text-3`）双主题。
- `ProjectHomeView.tsx` Tab 加「负载」（动态/计划/任务/**负载**/资产/讨论）+ 渲染 `<WorkloadView/>`。

## 验证（自动化）

- tsc 过；自动化驱动 App :5173 → 项目 → 负载 tab，断言工作量卡渲染 + 聚合数与 store 一致；0 报错；明暗双主题。

## 处理记录

2026-07-10 done：
- `ProjectWork.tsx` 加 `WorkloadView`（按 assignee 聚合根任务：头像+名+总数 + DOT 色状态分布堆叠条 + 待办/进行/完成率 + 逾期红 + Σ预估/Σ投入工时；`--card/--border/--border-2/--text-3` 双主题；`pj-empty` 空态）。
- `ProjectHomeView.tsx`：Tab 加「负载」（动态/计划/任务/**负载**/资产/讨论）+ 渲染 `<WorkloadView/>`（store 于项目进入即 loadWork，任一 tab 都有数据）。
- **自动化验证**：`npx tsc --noEmit` 过；programmatic 驱动 App :5173 → 项目 → 便签测试 → 负载 tab，卡片渲染「奇 · 10 项 · 待办 10 · 完成 0 · 0% · ⏱预估 6h·投入 2h」；后端 `/work-items` 聚合交叉核对完全一致（共10 待办10 预估6h 投入2h）；0 控制台报错。纯前端。
