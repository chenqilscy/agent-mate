---
id: WB-167
title: 认知记忆 档二 —— 本地嵌入 + 语义去重/自动更替 + 相关性检索注入
severity: P2
area: backend
origin: 既有实现
status: fixed
files:
  - backend/agent/mem_embed.py
  - backend/agent/memory.py
  - backend/storage/db.py
  - backend/requirements.txt
created: 2026-07-14
---

## 问题

见 epic [WB-165](WB-165-cognitive-memory-epic.md)。档二在档一（[WB-166](WB-166-memory-strength-decay-lifecycle.md)）之上加**本地语义**能力：
去重/更替从「精确字符串/LLM 序号」升级为「嵌入余弦相似度」，注入从「按强度取最近」升级为「按当前对话语义相关性 top-K」。

## 建议修法

1. **本地嵌入 provider**（`backend/agent/mem_embed.py`，仿 WB-139 ASR：可选依赖、懒加载单例、没装诚实降级）：
   `embed(text) -> list[float] | None`。首选 `fastembed`（ONNX runtime，`BAAI/bge-small-zh-v1.5`，无 torch、CPU 快、首用下载模型）；
   import 失败或模型不可用 → 返回 None（调用方回退档一非语义）。`requirements.txt` 加注释型可选依赖（同 faster-whisper 写法）。
2. **存储**：`store_memory` 把 embedding 存 `user_memories.embedding` BLOB（`np.asarray(vec, float32).tobytes()`）；读回 `np.frombuffer`。
3. **写入语义化**（AgentOS `service.write` 端口）：embed(content) → active 中取 top-1 余弦。
   sim≥0.98 且同文 → 强化既有；sim≥0.9 异文 → 插新 + 旧置 `superseded`+`superseded_by`。无嵌入则回退档一精确去重。
4. **检索注入语义化**（AgentOS `service.retrieve` 端口）：embed(当前 user_text) → active 余弦候选池(如 20) →
   按 `retrieval_score(sim, strength)` 重排 → top-K(如 5，且不超字符预算) → 命中强化。无嵌入/无 query 则回退档一强度排序。
5. **余弦**：numpy（已在 venv）；≤200 条全量算，无需向量库。

## 验证

- `py_compile`；装 fastembed 后隔离 DB 端到端：写「我在做 A 项目」→再写「我改做 B 工作台」应 supersede A（相似度触发）；
  近义「喜欢中文」/「偏好中文回复」被识别为高相似；检索「我在做什么项目」top1 命中 B。
- 无 fastembed 时回退档一，不报错（embed 返回 None、走强度排序）。
- 模型首次下载需联网一次；离线且未缓存 → 诚实降级。
- 装依赖后需**硬重启** backend（Windows 无 reload）。

## 处理记录（2026-07-14）

- 改动：
  - `backend/agent/mem_embed.py`（新）：懒加载 fastembed 单例（默认 `BAAI/bge-small-zh-v1.5`，ONNX、离线、零 API 成本），
    `embed`/`available`/`to_blob`/`from_blob`/`cosine`；没装/加载失败 → `_unavailable` 置真、`embed` 返回 None（诚实降级）。
  - `backend/agent/memory.py`：`store_memory` 加语义路径——embed(content) → 与 active 取最相似：≥0.98 且同文→强化；
    ≥0.90 且异文→插新 + 旧 supersede；否则纯插入。无嵌入回退档一精确去重。`build_memory_prompt` 加 `_rank_by_relevance`
    （embed(query) → retrieval_score(sim,strength) 重排）+ `_ensure_embeddings`（给缺 embedding 的旧记忆一次性回填，上限 64）；
    无 query/嵌入不可用回退档一强度排序。
  - `backend/agent/runtime.py`：注入传 `query_text=user_text`（按当前这轮对话检索）。
  - `backend/requirements.txt`：加可选依赖 `fastembed>=0.3`（注释说明没装则退档一）。
- 验证：
  - `py_compile` 过；`pip install fastembed==0.8.0` 成功；fastembed 支持 `BAAI/bge-small-zh-v1.5`。
  - 隔离 DB 端到端**全 PASS**：近义相似度 0.907 vs 无关 0.283；语义同文→强化不新增；语义近义异文→旧记忆 supersede 留链；
    无关事实各自保留；相关性检索（问「用什么编程语言」→ Rust 那条排最前）；遗留无-embedding 记忆注入时回填；无 query 回退档一。
  - **降级验证**：`MEM_EMBED_MODEL=bogus` → `available()=False`、`embed()=None` → store 精确去重 / 注入按强度，均不崩。
  - 端到端 live（真 /chat 语义注入）+ 硬重启在 epic 收尾统一实测。
- commit：（隔离 index，待提交）

