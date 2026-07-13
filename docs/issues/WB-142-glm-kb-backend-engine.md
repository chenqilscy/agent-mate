---
id: WB-142
title: GLM 知识库 Phase A —— 本地 backend 真·知识库引擎 + 路由
severity: P1
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/glm_kb.py
  - backend/routers/knowledge.py
  - backend/main.py
created: 2026-07-14
---

## 问题

本地 backend 没有 GLM 知识库客户端与路由，无法建库/传档/检索。

## 建议修法

**`backend/agent/glm_kb.py`**（同步 httpx，参 `backend/hub_client.py`）：
- 常量 `GLM_APP_BASE="https://open.bigmodel.cn/api/llm-application/open"`、`GLM_ZRAG_BASE="https://open.bigmodel.cn/api/zrag"`。
- `_headers(key)` → `Authorization: Bearer {key}`；统一解析 `{code,data,message}`，`code!=200` 抛 `GlmKbError`。
- `create_kb / list_kb / get_kb / update_kb / delete_kb / capacity / upload_file / upload_url / list_docs / delete_doc / retrieve / retrieve_multimodal`。

**`backend/routers/knowledge.py`**（`prefix="/api/knowledge"`，`current_user()` 取 owner，key 用 `db.get_provider_key(owner_id,"zhipu")`，仿 `routers/models.py`）：
- `GET /` `POST /` `GET|PATCH|DELETE /{id}` `GET /capacity`；`POST /{id}/documents`（UploadFile）、`POST /{id}/documents/url`、`GET /{id}/documents`、`DELETE /documents/{doc_id}`；`POST /retrieve`、`POST /retrieve/multimodal`。
- 没配 key → 可读错误「请先在『模型管理』给『智谱 AI·GLM』配置 API Key」。
- `backend/main.py` `include_router(knowledge.router)`。

## 验证

`py_compile agent/glm_kb.py routers/knowledge.py main.py`；硬重启 :8000 后 `POST /api/knowledge` 建库 →
`POST /{id}/documents` 传小文件 → `GET /{id}/documents` 轮询 `embedding_stat` → `POST /api/knowledge/retrieve` 看命中片段。

## 处理记录（2026-07-14）

- 改动：
  - 新增 `backend/agent/glm_kb.py`：同步 httpx 客户端（参 hub_client），常量 GLM_APP_BASE/GLM_ZRAG_BASE，`GlmKbError`，`_unwrap` 解析 `{code,data,message}`；函数 create/list/get/update/delete_kb、capacity、upload_file（原始 bytes+multipart files 转发 GLM）、upload_url（`upload_detail[]`）、list_docs、delete_doc、retrieve、retrieve_multimodal（/api/zrag）。
  - 新增 `backend/routers/knowledge.py`（`/api/knowledge`）：全端点，key 走 `db.get_provider_key(owner,"zhipu")`，没配 400 引导；同步调用统一 `run_in_threadpool`，`GlmKbError→502`。上传端点仿 `files.py` 原始流式（不引 python-multipart，文件名走 query），50MB 上限。
  - `backend/main.py`：`include_router(knowledge.router)`；BodySizeLimitMiddleware 豁免 `/api/knowledge/{id}/documents`（大文件不被 8MB JSON 限制误 413）。
- 验证：`py_compile` 全过；导入干净无循环依赖。**真机端到端（配了真智谱 Key）全通**：`POST /api/knowledge` 建库→`POST /{id}/documents` 传 md/txt→轮询 `embedding_stat`→`POST /retrieve` 精准召回（score 1.0，返回含「Python FastAPI / 端口 8000」的片段）→`DELETE` 清理。测试库均已删除。
- **实测发现并修复**：不传 `knowledge_type`（GLM 动态解析）会让向量化报「文档损坏」`word_num=0`；已把 `glm_kb.upload_file` 默认 `knowledge_type=5`+`sentence_size=300`，Embedding-2/3 中英文 txt/md 均正常向量化。上传路径豁免 main.py 的 8MB JSON 限制中间件。
- commit：待提交（WB-141 组）。
