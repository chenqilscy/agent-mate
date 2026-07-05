---
id: WB-030
title: 计划 · 计划项作为可执行任务交给 agent，agent 能查看并回写其状态
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/tools.py
  - backend/agent/runtime.py
  - src/stores/loadoutStore.ts
  - src/lib/sse.ts
  - src/components/project/ProjectWork.tsx
created: 2026-07-06
---

## 问题

WB-029 让待办作为 `🔖` 引用 chip 进入 Composer，但 agent 拿到后**只能读文本、不能操作计划项**。
参考 WorkBuddy（用户截图）：待办作为任务交给 agent → agent `todo show` 看详情、`todo transition`
把状态流转到「完成」→ 看板回写。那套来自外部 MCP `wb-issues`（`todo_<id>` 任务系统），
我们仓库没有；我们的 agent 是自研内置工具循环。目标：在**我们的 `work_items`** 上复刻该能力。

## 触发场景

项目 → 计划 → 待办详情「添加到输入框」→ 让 agent 处理该待办 → 完成后，看板上该待办**不会**
自动流转到「完成」，agent 也没有工具去改它。

## 影响

P2：计划项与 agent 执行断链——加进输入框的待办只是文本，agent 干完不能回写状态，形不成闭环。

## 建议修法（已确认：内置工具 + 可改任意状态、流转前不问）

**后端**
- `tools.py`：加 `_work_ctx` contextvar + `set_work_context(project_id, owner_id)`（仿 sandbox root）；
  新增两个内置工具——
  - `list_work_items()`：列当前项目计划项（id/标题/状态），只读。
  - `set_work_item_status(item_id, status)`：改状态（接受 待开始/进行中/暂停/完成 或 en 键），
    经 `db.get_work_item(owner 校验) + project_id 校验` 后 `db.update_work_item`，emit 一条 step trace。
  - `work_item_tools(plan)`：plan 模式只给只读的 `list_work_items`，完整模式给两者。
- `runtime.py`：`run_chat` 设 `set_work_context(session.project_id, user.id)`；仅当 `session.project_id`
  时把 `work_item_tools(plan)` 并入 toolset；`kind=='todo'` 的 ref 渲染成「关联待办任务（id=…）」块并附
  “完成/推进后调用 set_work_item_status 更新状态”提示；项目态补一句 system 提示。

**前端**
- `loadoutStore.AttachedRef` 增 `itemId?`；`sse.ts` refs 类型增 `kind?`/`itemId?`（透传，`refs: list[dict]` 后端已放开）。
- `ProjectWork.TodoDetailModal.addToInput` 传 `kind:'todo', itemId: item.id`。
- 看板回写：agent 改状态后，回到「计划」看板时 `workItemStore` 重拉即体现（必要时补一次刷新）。

## 验证

- `py_compile` + `npx tsc --noEmit` 过。
- 真实 LLM 跑一遍：把某待办「添加到输入框」→ 让 agent 完成 → agent 调 `set_work_item_status` 置「完成」→
  trace 出现「计划项『…』→ 完成」→ 回到看板该卡片在「完成」列。owner/项目越权被拒。
- 不在项目中的 ad-hoc 会话不暴露这两个工具、不误伤。

## 处理记录（2026-07-06）
- 改动：
  - 后端 `tools.py`：`_work_ctx` contextvar + `set_work_context`；`list_work_items`（只读）、`set_work_item_status`（接受中/英状态、owner+project 校验、emit step trace）两个内置工具；`work_item_tools(plan)`（plan 模式只给只读）。
  - 后端 `runtime.py`：`run_chat` 调 `set_work_context(session.project_id, user.id)`；仅项目态并入 `work_item_tools`；`kind=='todo'` 的 ref 渲染成「关联待办任务（id=…）」块并附回写提示；项目态补 system 提示。
  - 前端：`loadoutStore.AttachedRef` 增 `itemId?`、`sse.ts` refs 类型增 `kind?/itemId?`（透传）；`ProjectWork.addToInput` 传 `itemId: item.id`。
  - 看板回写：App `switch(view)` 使 `ProjectHomeView` 从 projexec 返回时重挂载 → `loadWork` 重拉，看板即时体现。
- 验证：`py_compile` + `npx tsc --noEmit` 过；工具单测（中文状态流转 db→done、owner 越权被拒、非法状态被拒、无上下文拒绝）通过；**真实 LLM 跑通**——把「整理会议纪要」加到输入框→发送「标记为完成」→ agent 调 `set_work_item_status`，trace 出现「计划项『整理会议纪要』→ 完成」，回复「已更新为完成 ✅」，DB status=done，返回看板卡片落在「完成」列。
- commit：（待提交）
