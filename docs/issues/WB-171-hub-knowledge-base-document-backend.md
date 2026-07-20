---
id: WB-171
title: Hub 真·知识库 + 文档后端（项目级）—— 建库/传档/维度锁，Manager 不算向量
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - hub/db.py
  - hub/config.py
  - hub/routers/knowledge.py
  - hub/main.py
created: 2026-07-14
---

## 问题

AgentMate Manager（Hub 控制平面）需要管理**真·知识库及其文档**，但 Hub **完全没有** KB/文档后端——
只有 `catalog_items` 里的 `KB_TPLS` 模板卡（WB-145/169），且 Hub 至今**不存任何文件**、不持 LLM key。
用户诉求（配套前端 [[WB-172]]）：项目级知识库，建库时配**向量维度**（下拉，有文档后锁定）+**切片方式**（下拉），
**上传/列/删文档（真存字节）**，但 **Manager 不调模型算向量**（向量化是未来执行面的事）。

## 触发场景

Manager 里进一个项目 → 想建知识库、传文档 → 没有任何后端接口可用。

## 影响

P2：净新增能力。无正确性风险，但没有后端前端就无从做起。项目级资源，需按项目角色门禁（照 work_items）。

## 建议修法

**范围仅 `hub/`。** 照 `hub/routers/work_items.py` + `hub/db.py` 既有范式：

1. **`hub/db.py`**：`init_db()` executescript 加两表 + 幂等 `PRAGMA table_info` 补列守卫（照 db.py:234-262）：
   - `knowledge_bases(id PK, project_id NOT NULL, name, description, icon, embedding_id INT, embedding_dim INT,
     knowledge_type INT, sentence_size INT, contextual INT, tags TEXT '[]', sort INT, created_at, updated_at)`
     + `INDEX(project_id, sort)`。
   - `kb_documents(id PK, kb_id NOT NULL, project_id NOT NULL, filename, size INT, content_type, doc_type,
     storage_path, vector_status INT DEFAULT 0, fail_msg, created_at)` + `INDEX(kb_id, created_at)`。
     `vector_status`：0 未向量化 · 1 已 · 2 失败。
   - DAO 照 work_items（db.py:808-891）：`create_kb/list_kbs/get_kb/update_kb(白名单+updated_at)/
     delete_kb(级联删文档行+磁盘文件)` + `create_kb_document/list_kb_documents/get_kb_document/
     delete_kb_document/count_kb_documents`。`embedding_dim` **服务端由 embedding_id 派生**（{3:1024,11:2048,12:2048}）。

2. **`hub/config.py`**：加 `STORAGE_DIR`（`HUB_STORAGE` 可覆盖，默认 `HUB_DIR/"storage"`）；`.gitignore` 加 `hub/storage/`。
   文件头注释澄清：KB 文档是用户显式放入共享控制面的资料（类比 WB-093 token 存 Hub），非沙箱文件。

3. **`hub/routers/knowledge.py`（新）**：`prefix="/api"`，挂 `/api/projects/{project_id}/knowledge-bases`，
   复用 work_items 的 `_access`（读）/`_require_write`（写，Viewer 403）：
   - KB：`GET` 列 · `POST` 建（派生 embedding_dim）· `GET {id}` · `PATCH {id}`（**若改 embedding_id/维度 且
     count_kb_documents>0 → 400「已有文档，向量维度不可更改」**）· `DELETE {id}`（级联）。
   - 文档：`GET {id}/documents` · `POST {id}/documents`（照 backend/routers/knowledge.py:109-140：`request.stream()`
     读原始 body、filename 走 query、≤50MB、扩展名白名单；**不引 python-multipart**）→ 存 `{STORAGE_DIR}/kb/{kb_id}/{doc_id}`、
     插元数据 `vector_status=0` · `DELETE documents/{doc_id}`（删文件+行）· `GET documents/{doc_id}/download`（流回）。
   - **Hub 永不设 vector_status=1**（诚实；执行面将来回写）。

4. **`hub/main.py`**：`app.include_router(knowledge.router)`。

## 验证

- `python -m py_compile` 改动的 hub `.py`。
- 隔离 Hub（HUB_DB/HUB_PORT/HUB_STORAGE=scratchpad）冒烟：注册账号→建项目→建 KB→传 .txt（字节真落 STORAGE_DIR）→
  列文档 vector_status=0→改维度被 400 拦→删文档（文件消失）→删库级联。断言磁盘真有字节、status 从不为 1。

## 明确不做

App/backend 拉 Hub KB+文档并用 owner 智谱 key 真向量化、回写 vector_status（未来执行面；本次只铺状态字段）。
**向量化只调 GLM 的嵌入模型接口（`/embeddings`）自算并自存向量，不使用 GLM 的知识库/RAG 功能**
（用户 2026-07-14 定向）。注：现有 App 侧 `backend/agent/glm_kb.py`（WB-141/142）目前**用的是 GLM 知识库
功能**，与此定向相悖，需另开 issue 迁移到「嵌入接口 + 自建向量库」——本次不动。

## 处理记录（2026-07-14）

- **改动**：
  - `hub/db.py`：executescript 加 `knowledge_bases` + `kb_documents` 两表（`CREATE TABLE IF NOT EXISTS`
    自动兼容存量库，无需 ALTER）；DAO `create_kb/list_kbs/get_kb/update_kb/delete_kb(级联返 storage_path)`
    + `count_kb_documents/create_kb_document(可传 doc_id 与文件名一致)/list_kb_documents/get_kb_document/
    delete_kb_document`；`KB_EMB_DIMS`+`kb_embedding_dim()` 服务端强派生维度（{3:1024,11:2048,12:2048}）。
  - `hub/config.py`：加 `STORAGE_DIR`（`HUB_STORAGE` 覆盖）；文件头注释澄清 KB 文档非沙箱文件。`.gitignore` 加 `hub/storage/`。
  - `hub/routers/knowledge.py`（新）：`/api/projects/{pid}/knowledge-bases` 全套，`_access`/`_require_write`
    门禁；PATCH 改维度且有文档 → 400 锁；文档 `request.stream()` 原始 body 上传（免 multipart）存
    `STORAGE_DIR/kb/<kb>/<doc>`，`vector_status=0` 恒定（Hub 永不置 1）；下载 `FileResponse`；删文档/库连带删盘。
  - `hub/main.py`：注册 knowledge 路由。
- **验证**：`py_compile` 4 文件过。隔离 Hub（HUB_DB/HUB_STORAGE/HUB_PORT=8109 scratchpad）Node 冒烟全通：
  建库 embedding_dim=2048 派生正确；传 .txt 真落盘 69B（磁盘核对一致）；list vector_status=0；
  **有文档改维度 → 400「已有文档，向量维度不可更改」**；删文档→盘上文件消失；无文档改维度→200 且 dim→1024；
  删库级联+目录清；传 .exe→400 类型拦截。前端联调见 [[WB-172]]。
- **commit**：未提交（待用户要求）。
