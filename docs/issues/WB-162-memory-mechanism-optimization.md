---
id: WB-162
title: 记忆机制优化 —— 注入预算化 + 结构化抽取(合并/更替) + 抽取输入预算 + 手动编辑
severity: P2
area: fullstack
origin: 既有实现
status: fixed
files:
  - backend/agent/memory.py:27
  - backend/agent/memory.py:40
  - backend/agent/memory.py:69
  - backend/storage/db.py:2082
  - backend/storage/db.py:2109
  - backend/routers/memory.py:34
  - src/components/settings/SettingsModal.tsx:113
created: 2026-07-14
---

## 问题

WB-148 的用户记忆机制能跑通（抽取/去重/注入/增删清都真持久化），但三处「机制」在记忆条数增长后会退化：

1. **注入无预算**（`backend/agent/memory.py:27` `build_memory_prompt`）：每轮把**全部**已存记忆（最多 `_MEMORY_MAX=200` 条）无脑拼进 system prompt。注入 token 随记忆数线性增长，且无优先级——手动记忆与陈旧对话记忆同等对待，200 条时可达数千 token/轮。

2. **软去重不可靠 + 无合并/更替**：
   - `backend/storage/db.py:2109` `add_memory` 只做 casefold+strip 的**精确**去重。语义近似（"喜欢用中文" vs "偏好中文回复"）各存一条。
   - `backend/agent/memory.py:40` 抽取器靠 prompt「不要重复」做**软**去重，不可靠。
   - 更关键：**过时/矛盾的事实只会追加、不会更替**。"用户在做 A 项目" 之后变成 "用户在做 B 项目"，两条并存，注入时自相矛盾。用户只能手动删。

3. **抽取输入无界**（`backend/agent/memory.py:69` `extract_and_store`）：把**全部**已有记忆塞进抽取 prompt 当「已有记忆」做软去重上下文，抽取这一轮 LLM 调用的输入也随库增长而变贵。

此外 API/前端**只能增/删/清，不能编辑一条**（`routers/memory.py`、`SettingsModal.tsx` MemoryPanel），修正一条记忆得先删再加。

## 触发场景

- 开启「生成对话记忆」，多轮对话后积累 40+ 条记忆 → 之后**每轮**都把这 40+ 条全量注入 system prompt，且抽取时全量回喂，token 与成本双线性增长。
- 对话里先说"我在做 WorkBuddy Hub"，几天后说"我现在主做 PM 工作台" → 抽取得到新事实**追加**，旧的"在做 Hub"仍在库并继续注入，模型收到互相矛盾的两条。
- 手动加了"我是前端工程师"，后来想改成"我是全栈工程师" → 无编辑入口，只能删掉重加。

## 影响

P2：功能可用不阻塞，但记忆越用越多时（正是"对话越多越懂你"想鼓励的路径）注入 token/抽取成本无界增长、且矛盾事实累积会**降低**记忆质量——与该功能目标背道而驰。local-first 尊重 API 花费是铁律，注入/抽取的 token 膨胀直接违背它。

## 建议修法

1. **注入预算化**（`build_memory_prompt`）：按字符预算（约 1500 字符）注入，优先级 = 手动(manual) 优先、其次按最近；超预算截断并注明"（更多较早记忆已省略）"。
2. **抽取产出结构化操作**（`_EXTRACT_SYS` + `extract_and_store`）：抽取器输出 JSON 数组，每项 `{"op":"add"}` 或 `{"op":"update","ref":<既有记忆序号>}` + `content`。给抽取器的「已有记忆」带**稳定序号**；`op:update` 且 `ref` 命中 → 原地更替那条（保留 id，内容换新，source 记 conversation）。`op:add` 走既有精确去重兜底。这一改同时解决"软去重不可靠"与"无更替"。
3. **抽取输入预算化**：只把最近 N 条（按同一字符预算）已有记忆带序号给抽取器。
4. **DB**：加 `update_memory(owner_id, mem_id, content)`（带去重守卫：更成与他条重复则视为删除该条）。
5. **API + 前端**（补齐"无编辑"）：加 `PUT /api/memory/{id}`；MemoryPanel 每条记忆加内联编辑（复用既有 `np-input` / `set-mem-*` class 与 token，明暗双主题都要看，勿引入新硬编码样式）。

不改 SSE 事件、不改注入/抽取默认关的 local-first 策略。

## 验证

- `cd backend && ./.venv/Scripts/python.exe -m py_compile agent/memory.py storage/db.py routers/memory.py` 过。
- `npx tsc --noEmit` 过。
- 单元/脚本：造 >预算 的记忆，断言 `build_memory_prompt` 输出被截断且含"省略"提示、手动记忆优先出现。
- `extract_and_store`：喂一段与既有某条矛盾的对话，断言产出 `update` op 且该条被原地更替（id 不变、内容换新、库里不新增矛盾条）；喂全新事实断言 `add`。
- API：`PUT /api/memory/{id}` 改内容成功、改成与他条重复时的守卫行为符合预期。
- 前端浏览器实测：MemoryPanel 内联编辑保存/取消，明暗双主题各看一遍。
- 回归：注入/抽取默认关时零变化；关掉开关不触发抽取。

## 处理记录（2026-07-14）

- 改动：
  - `backend/storage/db.py`：新增 `update_memory(owner_id, mem_id, content)` —— 原地更替内容、保留 id/source/created_at，带「更成与他条重复 → 不改返回 None」去重守卫。
  - `backend/agent/memory.py` 重写：
    - `INJECT_CHAR_BUDGET=1500` / `EXTRACT_CTX_BUDGET=1500` 两处预算常量；`_prioritize`（手动优先+最近优先）+ `_within_budget`（贪心取、至少 1 条、返回省略数）。
    - `build_memory_prompt` 按预算注入，超预算截断并注明「（另有 N 条较早记忆已省略）」。
    - `_EXTRACT_SYS` 改为产出**结构化操作数组**（`add` / `update` + `ref` 序号）；`_parse_ops` 替代 `_parse_facts`（容忍 ```json 包裹、纯字符串数组当 add、非法 ref 退化为 add）。
    - `extract_and_store`：回喂抽取器的「已有记忆」按预算截断并 1-based 编号；`update` 命中序号 → `db.update_memory` 原地更替，越界/被守卫挡下则退化为 `add`。签名不变，`runtime.py` 调用零改。
  - `backend/routers/memory.py`：新增 `PUT /api/memory/{mem_id}`（编辑一条；空/不存在/重复 → 400）。
  - `src/lib/api.ts`：新增 `editMemory(id, content)` → `PUT /memory/:id`。
  - `src/components/settings/SettingsModal.tsx` MemoryPanel：每条记忆加 ✎ 内联编辑（输入框 + ✓保存/×取消，Enter 保存 / Esc 取消），复用既有 `np-input`/`set-mem-*` class 与 token，无新样式。
- 验证：
  - `py_compile agent/memory.py storage/db.py routers/memory.py` 过；`npx tsc --noEmit` 过。
  - 隔离 scratchpad DB 单测 32 项全 PASS：注入预算截断+手动优先、`update_memory` 五类边界（成功/空/不存在/重复守卫/守卫后不变）、`_parse_ops` 八种输入、`extract_and_store` 结构化操作（update 原地更替不新增 / add 新增 / 越界 ref 退化 add / 重复 add no-op / 空数组 no-op / 抽取上下文受预算约束）。
  - 硬重启 :8000（Windows 无 reload）后实测 `PUT /api/memory/{id}`：编辑成功（id+source 保留）、改成与他条重复 → 400。
  - Playwright 浏览器实测 MemoryPanel 内联编辑：进入编辑→改→保存持久化→回显示态；取消丢弃改动回原文；**明暗双主题**各截图确认输入框深底浅字（`body.dark` 变量覆盖生效）、✎/✓/× 图标均清晰可读，无白底白字。
  - 清理：测试记忆已从真库删除、临时截图已删。
- commit：（待用户确认后提交）

