---
id: WB-168
title: 认知记忆 档三 —— 白盒管理（API 扩展 + 设置·记忆面板升级）
severity: P2
area: fullstack
origin: 既有实现
status: fixed
files:
  - backend/routers/memory.py
  - backend/storage/db.py
  - src/lib/api.ts
  - src/lib/types.ts
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

见 epic [WB-165](WB-165-cognitive-memory-epic.md)。档一/档二把记忆升级为强度/衰减/语义/软状态后，
需把这些「白盒」暴露给用户管理——参考 AgentOS `packages/api/src/routes/memory.ts` 的白盒路由 + 白盒页。

## 建议修法

1. **API 扩展**（`backend/routers/memory.py` + 对应 `db.py` 查询）：
   - `GET /api/memory`：列 active，每条带 `importance/usage_count/status/strength(现算)/last_used_at`。
   - `GET /api/memory/stats`：总数/active/archived/superseded、平均强度、衰退中(strength<0.1)数。
   - `POST /api/memory/search {query}`：语义检索 playground（只读，返回 sim/strength/score），无嵌入回退关键词。
   - `PATCH /api/memory/{id}/importance {importance:0..1}`。
   - `POST /api/memory/{id}/archive` / `POST /api/memory/{id}/rollback`（archived/superseded → active）。
   - `GET /api/memory/{id}`：详情 + 溯源链（supersededBy / superseded）。
   - `GET /api/memory/decaying?threshold`：衰退预览。
   - 保留 WB-148/162 的 add/edit/delete/clear/enabled。
2. **前端**（`SettingsModal.tsx` MemoryPanel + `api.ts`/`types.ts`）：升级为白盒面板——
   检索框（playground）、每条记忆的强度条 + 重要度可调 + 状态徽标（活跃/已归档/已更替）、归档/回滚按钮、
   溯源查看、衰退预览分区。**复用既有 `set-*`/`np-*` class 与 token**，明暗双主题都看，勿引入不协调硬编码样式。

## 验证

- `py_compile` + `tsc --noEmit`。
- API 逐个实测（stats/search/importance/archive/rollback/trace/decaying）。
- Playwright：检索 playground 出结果、调重要度后强度条变化、归档→列表移出+可回滚、溯源链正确；**明暗双主题**。

## 处理记录（2026-07-14）

- 改动：
  - `backend/storage/db.py`：`find_superseded_by`（溯源：找被某新记忆取代的旧记忆）。
  - `backend/agent/memory.py`：白盒服务 `strength_of`/`list_with_strength`/`memory_stats`/`search_memories`（语义检索 playground，返回 sim/strength/score，无嵌入关键词兜底）。
  - `backend/routers/memory.py` 重写：GET `?status=` + stats/search/decaying/detail(溯源)/importance(PATCH)/archive/rollback，保留 add/edit/delete/clear/enabled；固定路径声明于 `/{mem_id}` 前防路由遮蔽。
  - `src/lib/types.ts`+`api.ts`：MemoryItem 扩字段 + MemoryStats/SearchHit/Trace 类型 + memoryStats/searchMemory/setMemoryImportance/archiveMemory/rollbackMemory/memoryDetail。
  - `src/styles/app.css`：白盒类（强度条/重要度滑杆/统计/视图 pill/检索卡/溯源）—— 复用 `--brand/--chip/--border` token，明暗自适应。
  - `src/components/settings/SettingsModal.tsx` MemoryPanel 升级为白盒：概览统计 + 语义检索 playground + 活跃/已归档/已更替视图 + 每条强度条·重要度滑杆·状态徽标·归档/回滚·溯源。
- 验证：
  - `py_compile` + `tsc --noEmit` 过；硬重启 :8000（fastembed 真加载，stats.semantic=true）。
  - **live API 全通**：加 3 条记忆→stats(3活跃/均强65%/语义已启用)；语义 search「用什么编程语言」→ Rust 排最前(sim0.68)；PATCH 重要度 0.5→0.95(strength 同步)；archive→?status=archived 可见→rollback→active；detail 溯源。
  - **Playwright 白盒 UI 明暗双主题**：面板/检索结果/强度条/重要度滑杆/视图 pill/徽标均清晰，暗色无白底白字（复用 token 生效）。
  - **live 端到端语义注入（epic 收尾）**：真 /chat 问「我最喜欢的编程语言」→ 模型答「根据记忆，是 Rust」——该事实仅存于被语义注入的记忆，证明 runtime 注入链路真生效。测试记忆（含虚构事实）已清空、临时截图已删。
- commit：（隔离 index，与关闭 epic WB-165 同一提交）

