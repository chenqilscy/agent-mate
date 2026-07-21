---
id: WB-242
title: Session 执行缺少独立 Run 与可验收 Artifact 交付内核
severity: P1
area: fullstack
status: fixed
origin: WB-239 R1
files:
  - backend/storage/db.py:134
  - backend/storage/models.py:41
  - backend/agent/runtime.py:195
  - backend/routers/sessions.py:52
  - src/lib/types.ts:88
created: 2026-07-21
---

## 问题

AgentMate 当前把一次执行状态挂在 `sessions` 上，文件结果仅以消息里的 `diff.file` / `artifact` 事件临时展示；
没有稳定的 Run 生命周期、Artifact manifest、校验和、验收状态与恢复入口。一个 Session 不能可靠表达多次执行，
项目工作项也无法引用一次具体执行及其交付物。

## 触发场景

用户在同一会话中先生成文件、修改后再次执行，再回到首页或项目页查看结果。系统只能按会话和消息猜测最近交付，
无法区分两次执行、判断哪份文件已验收，也无法在失败后从对应 Run 恢复。

## 影响

P1：WB-239 的任务交付主线没有真实领域对象，办公文件、自动化可靠性、工作项协作、能力发布评测和多 Agent
都缺少可复用的运行与产物契约；继续在消息 UI 上叠加状态会造成不可追溯的数据分叉。

## 建议修法

- 新增本地权威 `runs` 与 `artifacts`，通过外键关联 Session、Project、WorkItem，并提供幂等迁移；
- Run 使用明确生命周期，结构化记录计划、错误、耗时、token、工具调用、权限快照与检查点；
- Artifact manifest 记录类型、路径、来源工具、大小、SHA-256、校验结果、预览与验收状态；
- `run_chat` 每次真实执行创建/推进 Run，写文件等真实工具事件登记 Artifact，SSE 暴露稳定 `run_id` / `artifact_id`；
- 提供按权限过滤的 Run/Artifact API，以及验收、拒绝、重试/恢复所需的最小契约；
- 建立离线黄金任务回归夹具，覆盖多次 Run、文件交付、哈希校验、权限隔离、失败恢复和验收。

## 验证

- 同一 Session 可产生多条独立 Run，状态迁移非法时被拒绝；重放同一执行键不会重复创建；
- 写入真实沙箱文件后产生可持久化 Artifact，路径受项目沙箱约束，哈希/大小与磁盘一致；
- Artifact 可按 accept/reject 验收，Viewer 只读，其他 owner/project 无法读取或修改；
- Run 失败保存结构化原因并可重试为新 Run，保留 `retry_of` 关系；
- 后端回归、前端类型检查、生产构建和真 API 请求通过，不依赖伪造 LLM 输出。

## 处理记录（2026-07-21）

- 数据与契约：新增本地权威 `runs` / `artifacts`，落实 Run 生命周期、owner 级幂等键、重试来源、
  workspace、WorkItem 关联、权限/loadout 快照、计划、checkpoint、错误、token 与工具调用统计；
  Artifact manifest 持久化 MIME、大小、SHA-256、校验和验收状态。
- 执行链路：每次真实 `run_chat` 创建独立 Run；等待人工输入、错误、断流、停止和完成均推进结构化状态；
  `write_file` 的真实输出登记 Artifact，并通过新增 `run` / 扩展 `artifact` SSE 同步到前端 trace。
- API 与权限：新增 Run 查询、Artifact 校验/验收和失败 Run 重试 API；个人 Run 仅 owner 可见，项目成员可读，
  Viewer 不可验收；全部 Artifact 接口实时复核文件存在性、大小与哈希。
- 自动验证：新增 6 项离线回归，覆盖幂等、非法状态迁移、指标、Artifact 更新与验收、重试关系、项目隔离、
  Viewer 门禁及 mock LLM→真 `write_file`→SSE/DB 全链；全量 regression 45/45、`tsc --noEmit`、
  Python compile 与 Vite 生产构建通过。
- 真机验收：硬重启 `:8101` 后，真实 LLM 会话完成且相同 idempotency key 重放保持 1 Run/2 messages；
  真实 LLM 调用 `write_file` 产生 1 个 Artifact，API 复核 exists/hash_matches 均为 true，验收后
  Artifact/Run 分别进入 accepted；专用临时会话与文件均已清理。
