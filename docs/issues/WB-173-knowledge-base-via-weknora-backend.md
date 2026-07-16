---
id: WB-173
title: 知识库改用自托管 WeKnora（后端 + 部署）—— 后端当 WeKnora 客户端，替换 GLM 托管 KB
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/weknora.py
  - backend/routers/knowledge.py
  - backend/agent/tools.py
  - backend/config.py
  - backend/agent/glm_kb.py
  - docs/weknora-部署.md
created: 2026-07-14
---

## 问题

用户定向：知识库不绑 GLM 托管 KB，改用**自托管的 WeKnora**（腾讯开源 RAG，Docker Compose 私有化部署）。
现状 App 侧知识库（`routers/knowledge.py` → `agent/glm_kb.py`）整套用 GLM 托管 KB（`/api/llm-application/open` + `/api/zrag`）。
需把后端改成 **WeKnora 的客户端**：指向本机 `:8080`、`X-API-Key` 鉴权、REST `/api/v1`。WeKnora 自己做解析/切片/嵌入/向量库/检索；
其嵌入 provider 定为 **GLM embedding-3 的 OpenAI 兼容接口**（复用现有 zhipu key，只调嵌入不碰 KB）。

## 影响

P2：功能性重构。自建方案（曾开 WB-173/174，已回退作废）不做。前端配套 [[WB-174]]。

## 建议修法

**范围 `backend/` + 一份部署文档。** 照 `glm_kb.py`/`hub_client.py` 的 httpx 客户端范式。

1. **`docs/weknora-部署.md`（新）**：Docker Compose 私有化部署指南——`.env`（`RETRIEVE_DRIVER=postgres` 自带向量库、
   `STORAGE_TYPE=local`、`EMBEDDING_PROVIDER=openai` + `EMBEDDING_BASE_URL=https://open.bigmodel.cn/api/paas/v4` +
   `EMBEDDING_MODEL_NAME=embedding-3` + `EMBEDDING_API_KEY=<zhipu>`、随机 `WEKNORA_API_KEY/SYSTEM_AES_KEY/JWT_SECRET`）、
   `docker compose up -d`、`:80` 注册取 API Key、`POST /api/v1/models` 注册 embedding-3 取 `embedding_model_id`、验证 curl。
2. **`backend/agent/weknora.py`（新）**：`X-API-Key` httpx 客户端——`create_kb/list_kb/get/update/delete`、
   `upload_file`(multipart 字段 `file` → `POST /knowledge-bases/:id/knowledge/file`)、`list_docs`(读 parse_status)、`delete_doc`、
   `search`(`POST /api/v1/knowledge-search {query, knowledge_base_ids}`) → 映射 **`[{text,score,metadata:{doc_name,doc_id}}]`**（旧 glm_kb.retrieve 同形状）。
3. **`backend/config.py`**：`WEKNORA_URL`(默认 http://localhost:8080)、`WEKNORA_API_KEY`、`WEKNORA_EMBEDDING_MODEL_ID`（backend-only，`.env`，铁律#4）。
4. **重写 `backend/routers/knowledge.py`**：glm_kb→weknora，保持路径/响应形状；`list_docs` 的 `parse_status`→`embedding_stat`
   （completed→1/failed→2/其它→0，前端 4s 轮询天然复用）；`retrieve`→weknora.search；删 GLM 专属 `retrieve/multimodal`、`upload_url`。
5. **`backend/agent/tools.py`**：`_knowledge_retrieve_run`→`weknora.search`（输出/`step` 事件/引用形状不变）。
6. **删 `backend/agent/glm_kb.py`**。

## 验证

- `py_compile`；WeKnora 跑起来后真机：建库→传 pdf/md→轮询 parse_status 到 completed→retrieve 命中且形状对→删档删库。
- **断言 WorkBuddy 全程只打 `:8080/api/v1`，无任何 GLM KB（/llm-application、/zrag）调用。**

## 处理记录

2026-07-16 · 接通真机 WeKnora 实例并接上后端。

**接入参数（用户提供 + 探测）**：WeKnora 跑在 `http://localhost:37200`（非默认 :8080），租户 API Key
`sk-BNM…`（只入 `backend/.env`，绝不提交/进前端）；实例已注册 GLM `embedding-3` 嵌入模型
（`668e2596-…`，dimension 2048）、glm-5.2/rerank 等。3 值写进 `backend/.env`（gitignored 已确认）。

**改动**：
- `backend/config.py`：新增 `WEKNORA_URL`/`WEKNORA_API_KEY`/`WEKNORA_EMBEDDING_MODEL_ID`（backend-only）。
- `backend/agent/weknora.py`（既有客户端，探测校准后**无需改请求映射**，仅增强）：加 `SUPPORTED_EXTS`、
  `default_embedding_model_id()`（.env 优先，缺则现取第一个 Embedding 模型）、`_err_msg()` 解析 WeKnora
  嵌套错误体 `{"error":{"message":…}}`。真实 envelope 确认为 `{data, success}`。
- 重写 `backend/routers/knowledge.py`：glm_kb→weknora，去掉 per-owner zhipu key（改后端单租户 key），
  `_require()` 未配 → 400 引导；`_kb_out`/`_doc_out` 映射（`knowledge_count`→document_size、
  `parse_status` completed/failed/其它 → embedding_stat 1/2/0）；删 GLM 专属 capacity/upload_url/multimodal。
- `backend/agent/tools.py`：`_knowledge_retrieve_run` glm_kb→weknora.search（输出/step/引用形状不变）。
- `backend/agent/glm_kb.py`：已无任何引用（dead code），留待提交时 `git rm`（工作树 dirty，删除被安全网关拦，改由提交处理）。

**验证**（真机，WeKnora :37200）：
- 直接驱动 `weknora.py`：list_models / create_kb / upload_file(md) / 轮询 parse_status pending→completed /
  search（映射 `{text,score,metadata:{doc_name,doc_id}}`）/ delete_doc / delete_kb —— **ALL GOOD**。
- 经运行中 backend（:8000，**硬重启**后才生效——命中「serving stale code」坑，重启前仍返回旧 GLM 数字 id）：
  `GET /api/knowledge` 返回真 WeKnora 库（UUID `002ce4ea…` koda/3 docs）；docs 映射 embedding_stat=1；
  `POST /retrieve` 3 命中（中文 body 须 `--data-binary @utf8file`，`-d` 直传中文会被 Git Bash GBK 化 → 400）；
  throwaway create→upload→poll(0→1)→delete 全通。
- agent `knowledge_retrieve` 工具：真检索 koda 库「三种通信方式」，返回带来源名 + 相关度的片段；未挂载态提示正确。
- `py_compile` 通过；断言 WorkBuddy 全程只打 `:37200/api/v1`，无任何 GLM KB 调用。

前端配套见 [[WB-174]]（已一并 fixed）。
