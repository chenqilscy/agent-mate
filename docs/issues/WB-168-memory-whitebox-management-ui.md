---
id: WB-168
title: 认知记忆 档三 —— 白盒管理（API 扩展 + 设置·记忆面板升级）
severity: P2
area: fullstack
origin: 既有实现
status: open
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
