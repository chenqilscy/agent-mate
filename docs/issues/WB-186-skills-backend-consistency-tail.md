---
id: WB-186
title: 技能后端一致性尾集 —— plan 模式不约束技能工具 / rankings 绕过 Manager 违反 WB-130 / 预览缓存无 TTL / schema 不去重
severity: P3
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/runtime.py:418
  - backend/agent/runtime.py:427
  - backend/agent/skills_store.py:360
  - backend/agent/skills_store.py:220
  - backend/agent/skills_store.py:369
  - backend/routers/skills.py:45
created: 2026-07-16
---

## 问题

一组独立的中低危一致性项（同 WB-160 的尾集范式）：

1. **`runtime.py:418` plan 模式约束不住技能工具（P2）**：
   ```python
   tools_list = base_tools(plan) + skill_tools + wi_tools + kb_tools
   ```
   `base_tools(plan)` 只对**基础工具**做 plan 过滤（`tools.py:544-545` 的 `_PLAN_TOOLS`），
   `skill_tools` **直接拼接、不受 plan 约束** → 只读规划模式下 `web_fetch` / `html_to_markdown`
   **照样发出网请求**。plan 模式的"只读"承诺对技能工具不成立。

2. **`skills_store.py:360-398` + `routers/skills.py:45-49` rankings 绕过 Manager（P3）**：
   `/api/skills/rankings` 走**本地 CLI 直连 skillhub.cn**，与同文件 `search`/`preview` 遵循的
   **WB-130「App 不直连 SkillHub，统一经 Manager」原则自相矛盾**。Hub 侧无对应 rankings 代理端点。

3. **`skills_store.py:220-221, 250-252` 预览缓存无 TTL（P3）**：
   `_preview_cache` 只在 `len > 64` 时整体 `clear()`，**无过期**。技能发新版后本进程永远返回旧预览。
   Hub 侧同名缓存有 `_PREVIEW_TTL = 300`（`hub/skillhub_client.py:260`）—— **两侧不一致**。

4. **`runtime.py:427-428` schema 不去重（P3）**：
   `active_tools`（L419）用 dict 按名去重，但 `schemas = [t.schema() for t in tools_list]`
   **不去重** → 技能工具与 base 工具重名时会向 LLM 发两份同名 schema。
   当前 3 个技能工具名无冲突，但无防护；WB-183 让技能定义可运营后，重名风险上升。

5. **`skills_store.py:369-372` 冗余（P3）**：`items = cached[1] if cached else []`
   在 `elif`/`else` 两分支重复写了两遍，可合并。

## 触发场景

1. plan（只读规划）模式下挂载「Web Access」技能 → 提问 → agent 调 `web_fetch` → **真发了出网请求**。
3. 预览某技能 → SkillHub 上该技能发新版 → 再次预览 → 仍是旧 SKILL.md，除非重启后端。

## 影响

P3（第 1 项本身接近 P2）。各自独立、中低危，合并为一组一致性修。
第 1 项是**行为承诺缺口**（plan 模式说只读却能出网），修复优先级最高。

## 建议修法

1. 技能工具也过 plan 过滤：给 `Tool` 加 `readonly: bool`（或复用 `_PLAN_TOOLS` 白名单机制），
   plan 模式下只保留只读技能工具；`analyze_csv`（纯本地读）可放行，
   `web_fetch`/`html_to_markdown`（出网）在 plan 下过滤掉。
2. Hub 加 rankings 代理端点（照抄 `catalog/skills/search` 范式），App 改为「Hub 优先 → 本地 CLI 兜底」，
   与 `search`/`preview` 口径统一（补完 WB-130）。
3. `_preview_cache` 加 `TTL = 300`，与 Hub 侧对齐。
4. `schemas` 改从 `active_tools.values()` 生成（已去重），或显式按 name 去重。
5. 合并那两行重复。

## 验证

- `py_compile` 过。
- plan 模式挂 Web Access 提问 → SSE trace 里**无 `web_fetch` 调用**；agent 模式下仍可调。
- 断开 Hub → rankings 仍能出内容（CLI 兜底）；接上 Hub → 走 Hub 代理（日志/抓包确认）。
- 预览缓存：mock 一次预览 → 等 TTL 过 → 再次预览确认重新取数。
- 造一个与 base 工具重名的技能工具 → 确认发给 LLM 的 schemas 只有一份。
