---
id: WB-166
title: 认知记忆 档一 —— 强度/衰减/使用强化 + 软状态生命周期（无嵌入）
severity: P2
area: backend
origin: 既有实现
status: fixed
files:
  - backend/storage/db.py:475
  - backend/storage/db.py:549
  - backend/agent/memory.py
  - backend/agent/runtime.py:254
created: 2026-07-14
---

## 问题

见 epic [WB-165](WB-165-cognitive-memory-epic.md)。档一移植 AgentOS 的强度/衰减/使用强化 + 软状态生命周期，**不含嵌入**。
现状：`user_memories` 只有 (id, owner_id, content, source, created_at)；注入按「手动优先+最近」；硬删/原地覆盖；`_MEMORY_MAX=200` 粗暴裁最旧。

## 建议修法

1. **schema 迁移**（`backend/storage/db.py` `_migrate_columns`，幂等 `PRAGMA table_info`+`ALTER`）：给 `user_memories` 补
   `importance REAL NOT NULL DEFAULT 0.5`、`usage_count INTEGER NOT NULL DEFAULT 0`、`status TEXT NOT NULL DEFAULT 'active'`、
   `superseded_by TEXT`、`last_used_at REAL`、`embedding BLOB`（本档不填，为档二预留）。
2. **强度纯函数**（Python 端口 `packages/core/src/memory/decay.ts`，放 `backend/agent/mem_decay.py`）：
   `recency_weight(age_ms, half_life=7d)` 指数半衰、`usage_boost(n)=1+ln(1+n)*0.2`、`compute_strength=clamp(importance×recency×usage_boost)`、
   `retrieval_score(sim,strength)`、`should_archive(strength,thr=0.05)`。
3. **service（memory.py）**：
   - `list_memories` 默认只列 `status='active'`；查询/更新带 status。
   - 落库改经 `store_memory(owner, content, source, importance)`：本档无嵌入 → 退回精确字符串去重（命中则强化 usage_count/last_used_at 而非跳过）。
   - 注入 `build_memory_prompt` 改为：active 记忆按 `compute_strength` 排序 → 取字符预算内 top-N → **命中强化**（usage_count++/last_used_at=now）→ 拼段。
   - 抽取 `update` 语义改为 **supersede**（旧记忆置 `superseded`+`superseded_by`=新 id，而非原地覆盖），保留留痕。
   - 新增 `decay_gc(owner)`：active 中 `should_archive` 的置 `archived`，返回归档数。停止「裁最旧 200」的硬删。
4. **runtime**：注入点不变（`runtime.py:254`），仅底层排序改为强度。

## 验证

- `py_compile`；隔离 DB 单测：强度函数（age=0→importance、age=半衰→半、usage 递增有上限）、强度排序注入、命中强化后 usage/last_used 变化、
  supersede 后旧记忆不再 active/不再注入但仍可查、`decay_gc` 归档弱记忆计数。
- 迁移幂等：旧库跑两次 init_db 不报错、列只加一次、存量记忆默认 importance=0.5/active。
- 回归：默认关记忆时零变化。

## 处理记录（2026-07-14）

- 改动：
  - `backend/storage/db.py`：`_migrate_columns` 加 `user_memories` 幂等补列（importance/usage_count/status/superseded_by/last_used_at/embedding）；
    记忆层重构——`list_memories`/`count_memories` 默认仅 active、返回全字段；新增 `get_memory`/`insert_memory`/`find_active_memory_by_content`/
    `reinforce_memory`/`supersede_memory`/`set_memory_status`(archive·rollback)/`set_memory_importance`/`list_active_with_embedding`/`set_memory_embedding`；
    `add_memory` 去掉「硬删最旧 200」、带 importance；`update_memory`(WB-162) 去重改只看 active、返回全字段。
  - `backend/agent/mem_decay.py`（新）：强度纯函数端口 AgentOS decay.ts —— recency_weight(指数半衰7天)/usage_boost(对数)/compute_strength/retrieval_score/should_archive。
  - `backend/agent/memory.py`：`build_memory_prompt` 改为 active 按强度排序取预算内 top-N + 命中强化；新增 `store_memory`(精确去重→强化 or 插入)、
    `decay_gc`(弱记忆软归档)；`extract_and_store` 的 update 改为 **supersede**（新记忆 + 旧软置 superseded 留链，不原地覆盖）。
  - `backend/agent/runtime.py`：抽取后顺手 `memory.decay_gc(user.id)`（best-effort）。
- 验证：
  - `py_compile` 过；隔离 scratchpad DB 单测 **36 项全 PASS**（强度纯函数 10 · 迁移幂等+新列默认 9 · 强度排序注入+命中强化 5 ·
    store_memory 去重强化 2 · 抽取 update→supersede 留链 5 · decay_gc 软归档+rollback 5）。
  - 硬重启 :8000 后 **live 冒烟**：迁移在真·已populated DB 上无报错（GET /api/memory 200）、新增记忆返回 importance/usage_count/status/superseded_by/last_used_at 全字段。
- commit：（与 WB-165 epic 登记同一提交，待提交）

