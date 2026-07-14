---
id: WB-170
title: 记忆嵌入后端可配置 —— 本地(fastembed) ⇄ 在线(GLM embedding-3) 用户可选
severity: P2
area: fullstack
origin: 既有实现
status: fixed
files:
  - backend/agent/mem_embed.py
  - backend/agent/memory.py
  - backend/storage/db.py
  - backend/routers/memory.py
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

系统有两套向量模型：**本地** fastembed `bge-small-zh`（记忆 WB-167 用）与**在线** GLM `embedding-3`（知识库 WB-141 用）。
用户要求「记忆」与「知识库」两个场景都能配置选哪种模式。

现状核对：
- **知识库侧已就绪**：建库/编辑本就支持 `embedding_id`（后端 `routers/knowledge.py` + `glm_kb.create_kb`），
  App 建库弹窗（`KnowledgeView.tsx` EMBEDDINGS 下拉：Embedding-3/3-pro/2）+ Manager 控制台（WB-169「向量维度」下拉）
  都已让用户选档位。**无需新做**。
- **记忆侧是缺口**：`mem_embed.py` 只有本地 fastembed，无法选在线 GLM embedding-3。本 issue 只补这一半。

## 建议修法

1. **嵌入 provider 抽象**（`backend/agent/mem_embed.py`）：按 owner 的设置选后端——
   - `local`：现有 fastembed（默认，local-first）。
   - `glm`：调 GLM `POST /api/paas/v4/embeddings`，model `embedding-3`（2048 维），key 用 `db.get_provider_key(owner,"zhipu")`（与知识库同源，绝不回前端）。没 key/请求失败 → 视为不可用。
   - 对外：`embed(owner_id, text)`、`embed_batch(owner_id, texts)`（GLM 批量省调用）、`model_tag(owner_id)`（如 `local:bge-small-zh-v1.5` / `glm:embedding-3`）、`active_backend(owner_id)`、`backends_status(owner_id)`（各后端是否可用，供 UI）。
2. **维度/模型不匹配处理**（关键坑：本地 512 维、embedding-3 2048 维，跨模型余弦无意义）：
   `user_memories` 加列 `embedding_model TEXT`（`_migrate_columns` 幂等）。存向量时连 model_tag 一起存；
   检索/去重只比对**与当前后端同 tag** 的向量；tag 不同或缺失的 → 当作「缺 embedding」由 `_ensure_embeddings` 用当前后端**重嵌入回填**。这样切后端后记忆惰性迁移、无需一次性重算。
3. **config + API**：user_setting `pref.embed_backend`（'local'|'glm'，默认 local）；`memory_stats`/`GET /api/memory` 带 `embed_backend` + `backends`（可用性）；`PUT /api/memory/embed-backend {backend}`。
4. **前端**（设置·记忆）：加「记忆嵌入」选择（本地 / 在线 GLM embedding-3），标注在线需在「模型管理」配 GLM key；切换即生效（下次注入惰性重嵌入）。复用既有 set-*/np- class，明暗双主题。

不改知识库；local-first 默认仍本地、在线纯 opt-in。

## 验证

- `py_compile` + `tsc`；隔离 DB 单测：设 backend=local 存/检索用本地 tag；切 glm（stub GLM embeddings）后旧本地向量被重嵌入、tag 变 glm、跨 tag 不误比对；无 GLM key 时 glm 后端不可用、回退档一不崩。
- live：配了 GLM key 时切在线，检索 playground 出结果（sim 合理）；切回本地正常。
- 迁移幂等；默认关记忆/默认本地时零行为变化。

## 处理记录（2026-07-14）

- 现状核实：知识库嵌入档位选择**已就绪**（App `KnowledgeView.tsx` EMBEDDINGS 下拉 Embedding-3/3-pro/2 + Manager console WB-169 + 后端 create_kb/update_kb 早支持 embedding_id），本 issue 只补记忆侧。
- 改动：
  - `backend/storage/db.py`：`user_memories` 加 `embedding_model` 列（`_migrate_columns` 幂等）；`insert_memory`/`set_memory_embedding`/`list_active_with_embedding` 带 embedding_model tag。
  - `backend/agent/mem_embed.py` 重写为 **owner-aware 双后端**：`local`（fastembed bge-small-zh 512d）/ `glm`（GLM `/api/paas/v4/embeddings` model embedding-3 2048d，key 用 `db.get_provider_key(owner,"zhipu")`）；`configured_backend`/`set_backend`/`active_backend`（所选不可用回退另一个可用）/`model_tag`/`backends_status`/`embed(owner,text)`/`embed_batch`；不可用则诚实降级返回 None。
  - `backend/agent/memory.py`：store/`_ensure_embeddings`/`_rank_by_relevance`/`search_memories`/`build_memory_prompt` 全部按 owner 选后端；**只比对同 tag 向量，切后端后旧 tag 向量惰性重嵌入迁移**；`memory_stats` 加 `embed` 状态。
  - `backend/routers/memory.py`：`PUT /api/memory/embed-backend`；stats 带 embed 状态。
  - `src/lib/types.ts`+`api.ts`：`EmbedStatus` 类型 + `setEmbedBackend`。
  - `src/components/settings/SettingsModal.tsx`：设置·记忆加「记忆嵌入」选择（本地/在线 GLM embedding-3，未配 GLM 密钥时提示暂用本地），stats 行显示当前生效后端。
- 验证：
  - `py_compile` + `tsc` 过；隔离 DB 单测 **22 项全 PASS**（默认本地 512d / 切 glm 无 key 回退 local / 配 key+stub→glm 生效 2048d / 切后端旧向量跨-tag 重嵌入迁移 / 只同-tag 比对 / 无后端降级档一不崩 / 迁移列存在）。
  - 硬重启 :8000（迁移在真库无报错，stats 出 embed 状态，真用户 glm:true 即已配智谱密钥）。
  - **live 双后端实测**：本地检索 Rust sim 0.68；切在线→真 GLM embedding-3 检索 Rust sim 0.61（真实 URL/鉴权/2048维解析正确）；切回本地、清测试记忆。
  - Playwright：设置·记忆「记忆嵌入」下拉渲染正确、stats 显示「语义检索 本地」，复用 set-field/np-input（明暗自适应）。
- commit：（隔离 index，待提交）

