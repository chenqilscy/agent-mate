---
id: WB-150
title: 智能体设置真后端 —— 工具步数上限 + 回复发散度(temperature)，按 owner 存 KV 且 run_chat 真读真用
severity: P2
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/agent_settings.py
  - backend/agent/runtime.py
  - backend/routers/prefs.py
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

设置中心「智能体设置」tab 还是「即将上线」占位。做成**真生效**：把 runtime 里写死的
`MAX_ROUNDS=12`（工具循环轮数）与 stream_chat 的默认 `temperature=0.6` 变成**按 owner 可配**、
`run_chat` 真读真用的智能体行为设置（铁律#1，真持久化 + 真生效）。

## 触发场景

设置 → 智能体设置 → 把「最多连续工具步数」调到 3、「回复发散度」调到 0 → 新开对话，
agent 的工具循环最多 3 步、输出更确定；刷新/重开设置仍在。

## 影响

P2：让高级用户真正调节 agent 行为（步数省 token / 温度控发散），复用 WB-147 的 KV 样板。

## 建议修法

1. **`agent/agent_settings.py`**：键 `agent.max_rounds`/`agent.temperature`，
   `get_max_rounds(owner)`（默认 12，clamp [1,50]）、`get_temperature(owner)`（默认 0.6，clamp [0,2]）、
   `get_settings/set_settings`。复用 `db.get/set_user_setting`。
2. **`agent/runtime.py`**：循环上限改 `range(agent_settings.get_max_rounds(user.id))`；
   `stream_chat(..., temperature=agent_settings.get_temperature(user.id))`。
3. **路由**：`prefs.py` 加 `GET/PUT /api/settings/agent`（同一 settings 路由，owner 作用域，clamp）。
4. **前端**：`api.agentSettings/saveAgentSettings`；`SettingsModal` 智能体设置 panel——
   步数滑块/输入 + 温度滑块 + 保存，复用既有 class。

## 验证

- `py_compile` + `tsc`。
- PUT max_rounds=2 → 跑一个需要多步工具的任务，SSE 里工具步数 ≤2；PUT 回默认。
- PUT temperature 边界 clamp 正确；GET 回显。
- 明暗双主题看 panel。

## 处理记录（2026-07-14）

- 改动：
  - 新增 `backend/agent/agent_settings.py`：键 `agent.max_rounds`/`agent.temperature`，get/set + clamp（rounds[1,50] 默认 12、temp[0,2] 默认 0.6），复用 `db.get/set_user_setting`。
  - `backend/agent/runtime.py`：循环上限 `range(_max_rounds)`（读 `agent_settings.get_max_rounds(user.id)`）；`stream_chat(..., temperature=_temperature)`。原写死 `MAX_ROUNDS` 常量保留作默认参考。
  - `backend/routers/prefs.py`：加 `GET/PUT /api/settings/agent`（同 settings 路由，owner 作用域）。
  - 前端 `src/lib/{types,api}.ts`：`AgentSettings` + `agentSettings/saveAgentSettings`。
  - `src/components/settings/SettingsModal.tsx`：`AgentPanel`——步数滑块 + 温度滑块 + 保存/恢复默认（读后端 defaults/limits）；替占位。
  - `src/styles/app.css`：`set-slider/set-slval` 样式。
- 验证：
  - `py_compile` + `tsc` 过。
  - API：GET 默认(12/0.6)；PUT 越界 clamp（999→50、5→2.0）；PUT 2/0 持久化并回显。
  - **真生效行为证明**：默认工作空间植入含暗号 `ZXQW-7731-PLUM` 的 note.txt → 同一「读取并原样告知暗号」任务，`max_rounds=1` 最终答复**不含**暗号（封顶 1 轮、无汇报轮），`max_rounds=3` **含**暗号（读到并汇报）→ 步数上限真govern 工具循环。
  - CDP 明暗双主题实截 panel（双滑块+按钮，无坑）。
  - 清理：删 note.txt、agent 设置复位默认。
- commit：未提交（与 WB-151 一并，待用户确认）。
