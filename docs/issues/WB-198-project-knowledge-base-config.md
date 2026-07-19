---
id: WB-198
title: 项目配置缺少知识库挂载与持久化，项目执行无法自动使用项目知识
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/storage/models.py:55
  - backend/storage/db.py:130
  - backend/routers/projects.py:46
  - src/views/ProjectHomeView.tsx:157
  - src/components/project/NewProjectModal.tsx:21
created: 2026-07-20
---

## 问题

知识库与 `PickerOverlay(kind='kb')` 已真实可用，但项目数据模型只持久化连接器、专家和技能。
新建项目没有知识库选择行，项目右侧“项目配置”也不能维护知识库；进入项目时还会重置会话 loadout，
导致项目执行不会自动携带项目知识库。

## 触发场景

创建或打开项目 → 希望为项目挂载一个已有 WeKnora 知识库 → 项目配置中没有入口；
即使在普通会话临时选择过知识库，进入项目后也会被重置，执行时 `knowledge_ids` 为空。

## 影响

P1：项目指令、专家、技能可固定配置，唯独项目知识无法固化，RAG 只能每次手工选择，
项目工作台无法形成稳定上下文。

## 建议修法

- 本地 `projects` 增加非破坏迁移字段 `knowledge_ids`，更新模型、DAO、项目 API 与前端类型。
- 新建项目和项目配置复用已有知识库真列表/选择器，按 ID 持久化，显示名称并处理已删除库。
- 进入项目时把项目知识库同步到会话 loadout；每次项目执行都把这些 ID 传入现有 chat/SSE 链路。
- 知识库配置属于本机执行面，不向 Hub/Manager 上传；Hub 项目的本地知识库挂载在下行刷新后仍保留。
- Viewer 只读，Owner/Admin 才能修改，保持现有项目配置权限语义。

## 验证

- 数据库迁移不破坏旧项目，旧记录返回 `knowledge_ids: []`。
- 新建项目选择知识库 → API 回读一致；项目配置增删 → 刷新后仍一致。
- 项目执行请求真实携带持久化的 `knowledge_ids`，知识检索工具按挂载库可用。
- Hub-origin 项目的知识库 ID 不上传云端，pull 后本地挂载不丢失。
- 前端类型检查/构建、后端 `py_compile` 和项目 API 冒烟通过；明暗主题下检查知识库配置卡与选择器。

## 处理记录（2026-07-20）

- `projects` 非破坏迁移新增 `knowledge_ids`，模型、DAO、API 和前端类型全链路回读；旧项目实测均返回空数组。
- 新建项目和项目右侧配置复用现有真知识库列表/选择器，按 ID 保存并显示库名；Viewer 保持只读。
- 项目载入时同步知识库 loadout，后端 `run_chat` 再把项目挂载与本轮挂载去重合并，避免只靠前端状态。
- Hub 镜像更新不上传、不覆盖本地知识库挂载，保持 local-first 执行边界。
- 独立临时后端真实 API 测试 5 项通过：创建去重、GET/PATCH 回读、SQLite 真值、Viewer 403；生产库迁移与项目页明暗主题已实测。
- 后端 `py_compile`、前端类型检查与生产构建通过。

状态：`fixed`（本次提交，见 Git 历史）。
