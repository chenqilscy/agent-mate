---
id: WB-255
title: 项目工作项无法直接发起、跟踪和验收本地 Run 与 Artifact
severity: P1
area: fullstack
status: fixed
origin: WB-239 R3
files:
  - backend/routers/work_items.py:1
  - backend/routers/runs.py:1
  - backend/storage/db.py:1362
  - src/views/ProjectView.tsx:1
created: 2026-07-21
parent: WB-239
---

## 问题

Run 已能关联 `work_item_id`，Artifact 也有独立 manifest，但项目工作项页面仍只能改 PM 字段，无法从工作项
直接发起一次本地 Agent 执行、看到当前步骤与失败原因、打开交付物并验收回写。团队时间线与通知也没有围绕
WorkItem→Run→Artifact 的状态变化组织。

## 触发场景

项目成员打开一个待办，希望“交给 Agent 执行”并在同一工作项里跟踪；当前必须手工新建会话，再靠引用碰巧建立
关联，Run/Artifact 只能从其他入口查找，验收 Artifact 后工作项不会完成，也没有给项目成员留下可见摘要。

## 影响

P1：R3 团队协作主链断裂，WorkItem 与本地执行仍是两套产品；成员无法可靠判断谁发起、运行到哪、交付什么、
由谁验收，权限和 local-first 同步边界也无法端到端验收。

## 建议修法

- 新增 owner/member-scoped 工作项执行 API，以稳定幂等键创建项目 Session 并把 `work_item_id` 注入 Run；
- 工作项详情聚合关联 Runs、每个 Run 的 Artifacts、结构化失败/成本和验收状态；
- Artifact 全部通过后由有写权限成员显式“验收并完成”，事务性更新 Artifact/Run/WorkItem；
- Viewer 只读；Member/Admin/Owner 的发起、外部写与验收遵循项目角色和 Run 权限快照；
- 允许上云的状态摘要写项目时间线/outbox，禁止同步 prompt、正文、secret、沙箱路径和文件内容；
- App 工作项详情提供发起、跟踪、打开会话、查看/验收产物与失败恢复入口。

## 验证

- 从真实项目 WorkItem 发起后，Session/Run/work_item_id/permission snapshot 关联一致且重复请求不重复执行；
- 项目成员能看到真实 Run 与 Artifact，Viewer 无法发起或验收，非成员无法读取；
- 显式验收原子完成 Artifact→Run→WorkItem，失败时不留下半完成状态；
- Server/outbox 只有允许的 ID、状态、计数和摘要，不含私密正文/路径/secret；
- API 回归、真实 SSE、明暗主题、窄屏、TypeScript 与生产构建通过。

## 处理记录

- 2026-07-21：新增持久 `work_item_launches` 与幂等执行 API，建立 WorkItem→Session→Run→Artifact 关联，
  权限快照记录项目角色、工作项和发起人；真实 LLM 失败会回写失败 Run、暂停工作项并通知成员。
- 2026-07-21：工作项详情加入 Agent 发起、运行状态/成本/错误、产物下载与整体验收；验收在单事务中校验并
  更新全部 Artifact、Run 和 WorkItem，Viewer 只读、非成员不可见，上云 outbox 仅含 ID、状态、计数元数据。
- 2026-07-21：4 条协作回归覆盖幂等、权限、事务回滚和元数据边界；隔离真 API 验证失败链路；TypeScript
  与 Vite production build 通过。应用内浏览器完成深色、浅色和 860px 窄屏验收，并在隔离数据上确认
  点击验收后 `Run=accepted`、产物“已验收”、工作项“已完成”；临时数据库、工作区和进程均已清理。
