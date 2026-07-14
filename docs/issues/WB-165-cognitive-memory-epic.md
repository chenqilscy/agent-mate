---
id: WB-165
title: 认知记忆机制移植（参考 AgentOS）—— 强度/衰减/使用强化 + 本地语义检索 + 白盒管理（epic）
severity: P2
area: fullstack
origin: 既有实现
status: in-progress
files:
  - backend/agent/memory.py
  - backend/storage/db.py
  - backend/routers/memory.py
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

WorkBuddy 的用户记忆（WB-148 + WB-162 优化后）仍是「按最近/手动注入固定预算」的朴素机制：
去重靠精确字符串 + LLM 序号引用、注入与当前对话无关、无强度/衰减/使用强化、硬删除无留痕。
参考同仓库邻居项目 **AgentOS**（`D:\work\local\AgentOS`，`packages/core/src/memory/`）的「白盒认知记忆」，
把其成熟机制移植进来。经用户确认，采纳**全部三档**（累加式）。

AgentOS 记忆机制要点（`service.ts`/`decay.ts`/`store.ts`/`embedding.ts`）：
- 本地嵌入（transformers.js `bge-small-zh`，离线零成本）+ 余弦相似度检索。
- 写入：sim≥0.98 且同文 → 强化既有；sim≥0.9 异文 → 插新 + 旧记忆置 `SUPERSEDED`（版本化留链）。
- 强度：`strength = importance × recency(指数半衰期·默认7天) × usageBoost(对数)`。
- 检索：嵌入候选池 → 按 `相似度×强度` 重排 → topK → 命中即强化（usageCount++/lastUsedAt）。
- 衰退 GC：strength<阈值 → `ARCHIVED`（软归档，不硬删），可 `rollback`。
- 白盒管理 API：list/stats/search/溯源/编辑/调重要度/衰退预览/归档/回滚。

## 影响

P2：功能可用不阻塞。但这是一次质变——注入从「最近一批」变为「与当前对话语义相关的 top-K」，
既提质又省 token；强度/衰减让记忆自清理；软状态给可恢复的白盒管理。符合 local-first（嵌入走本地模型，
仿 WB-139 faster-whisper 先例：可选依赖、懒加载、没装则诚实降级为档一非语义模式）。

## 建议修法（分三档，各一个子 issue）

- **WB-166 档一（无嵌入·基础）**：`user_memories` 补列（importance/usage_count/status/superseded_by/last_used_at/embedding）
  经 `_migrate_columns` 幂等迁移；强度/衰减纯函数（Python 端口 decay.ts）；注入改为按强度排序取预算内 top-N + 命中强化；
  软状态生命周期（active/superseded/archived，停止硬删/原地覆盖，抽取更替走 supersede）；`decay_gc` 归档弱记忆。
- **WB-167 档二（本地语义检索）**：本地嵌入 provider（懒加载 fastembed/onnx `bge-small-zh`，没装回退档一）；
  embedding 存 BLOB（float32）；余弦（numpy）；写入语义去重/自动更替；注入改为 embed(当前 user_text) → 相似度检索 → `sim×strength` 重排 top-K。
- **WB-168 档三（白盒管理 UI）**：`/api/memory` 扩展（stats/search/importance/archive/rollback/trace/decaying）+
  设置·记忆面板升级为白盒（检索 playground / 重要度滑杆 / 强度条 / 状态徽标 / 归档·回滚 / 溯源链 / 衰退预览），复用既有 class。

**范围裁剪**（相对 AgentOS）：不移植 layer 分层（WorkBuddy 记忆单一为「用户事实」）、不移植 scope（用 owner_id 隔离已足）、
不移植 dream 睡眠整合（decay_gc 已够）。LLM 结构化抽取（WB-162）保留，只把落库改走新 service。

## 验证

各子 issue 分别验证；epic 关闭条件 = WB-166/167/168 全 fixed 且端到端实测：
开启记忆→多轮对话→记忆按相关性注入→矛盾事实自动更替→弱记忆随衰减归档→白盒 UI 可查可管，明暗双主题。
