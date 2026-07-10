---
id: WB-120
title: App 端 PM 对齐 Manager 片4 —— 任务列表增强（内联编辑状态/优先级 + 负责人头像）
severity: P2
area: frontend
status: fixed
origin: WB-117 App 对齐 epic 之片4；对齐 Manager 列表内联编辑
files:
  - src/components/project/ProjectWork.tsx
created: 2026-07-10
---

## 背景

App 的「任务」tab（TaskList）是只读平铺列表（状态点+标题+状态文字+删除），不能就地改。Manager 列表可点单元格内联改状态/优先级/负责人/里程碑（WB-114）。本片把 App TaskList 升级为可内联编辑——直接复用本文件已有的 `StatusPill/PriorityPill`（本就是带下拉的内联选择器，详情弹窗在用）。

## 建议修法

- `TaskList`：加 `update`；行内静态「状态点 + 状态文字 + 优先级点」替换为 `<StatusPill dir="down">`＋`<PriorityPill dir="down">`（点即改，`onPick → update`）；加负责人头像（`assignee_name` 首字），保留标题/标签/截止/删除。

## 验证（自动化）

- tsc 过；驱动 App → 任务 tab，断言行含状态/优先级 pill 可点开选项、改后 store/后端落库；0 报错；双主题。

## 处理记录

2026-07-10 done：
- `TaskList` 加 `update`；行内静态「状态点+状态文字+优先级点+ago」替换为标题/标签/截止 + 负责人头像(`wb-av` 首字) + `<PriorityPill dir="down">` + `<StatusPill dir="down">`（本文件已有的带下拉内联选择器，详情弹窗在用）+ 删除。点 pill 即改，`onPick → update`。
- **自动化验证**：`npx tsc --noEmit` 过；programmatic 驱动 App :5173 → 便签测试 → 任务 tab：10 行、每行 2 pill、标题(111/222/333)可见；点第一行状态 pill「待开始」→选「进行中」→行即更新、后端 `/work-items` item 111 status=doing 真落库（已重置回 todo）；0 控制台报错。纯前端。
