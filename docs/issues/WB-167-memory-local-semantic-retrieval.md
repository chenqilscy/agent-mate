---
id: WB-167
title: 认知记忆 档二 —— 本地嵌入 + 语义去重/自动更替 + 相关性检索注入
severity: P2
area: backend
origin: 既有实现
status: open
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
