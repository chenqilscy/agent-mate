---
id: WB-148
title: 记忆真后端 —— 对话记忆持久化 + 注入 agent（真生效）+ 开启后从对话自动抽取 + 前端记忆 tab
severity: P1
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/storage/db.py
  - backend/agent/memory.py
  - backend/routers/memory.py
  - backend/agent/runtime.py
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

设置中心「记忆」tab 还是「即将上线」占位。对齐高保真原型：记忆让 WorkBuddy 记住用户偏好/习惯，
对话越多越懂你——需要**真持久化 + 注入对话（真生效）+ 可从对话自动抽取**，不能是假开关（铁律#1）。

## 触发场景

设置 → 记忆 → 开「生成对话记忆」→ 聊几轮涉及个人偏好的话 → 回来看「记忆」列表出现新条目；
新开对话时 agent 已「记得」这些偏好。手动加/删记忆也应真生效、跨重启留存。

## 影响

P1：记忆是设置中心里用户预期最强的一项；复用 WB-147 的 KV + 注入样板，做成第二条全栈竖切。

## 建议修法

1. **DB**（`storage/db.py`）：新表 `user_memories(id, owner_id, content, source, created_at)` +
   helpers（list/add/delete/clear/count，按 owner）。
2. **`agent/memory.py`**：
   - `build_memory_prompt(owner)` —— 把已存记忆拼「# 关于用户的记忆」段注入 system prompt（有则注入，真生效）。
   - `capture_enabled(owner)` —— 读 KV `pref.memory_capture`（默认关：local-first 尊重用户 API 花费）。
   - `async extract_and_store(owner, user_text, assistant_text, *creds)` —— 一次性非流式 LLM 调用，
     抽 0–N 条「关于用户本人、长期有效」的事实，去重后入库；best-effort，失败不影响回复。
3. **`agent/runtime.py`**：注入 `build_memory_prompt`（个性化之后）；成功完成、有实质回复且开启抽取时，
   在助手消息持久化后（~601）跑 `extract_and_store`（复用已解析的模型凭据）。
4. **路由 `routers/memory.py`**：GET/POST/DELETE/clear + PUT enabled；`main.py` 注册。
5. **前端**：`api.memory*`；`SettingsModal` 记忆 tab 换真 `MemoryPanel`——开关 + 列表（内容/来源/删除）+
   手动添加 + 清空，复用既有 class。「从其他 AI 导入」暂无来源，诚实占位。

## 验证

- `py_compile` 后端；`tsc --noEmit`。
- 开启抽取 → 真跑一轮带个人偏好的对话 → 断言 `user_memories` 出现新条目；再开一轮断言记忆已注入生效。
- 手动加/删/清空经 API 生效、可回显。
- 明暗双主题看记忆 panel。

## 处理记录（2026-07-14）

- 改动：
  - `backend/storage/db.py`：新表 `user_memories(id, owner_id, content, source, created_at)` + helpers（list/count/add[去重·大小写不敏感]/delete/clear，按 owner，200 条上限）。
  - 新增 `backend/agent/memory.py`：`build_memory_prompt(owner)`（已存记忆拼「# 关于用户的记忆」注入）+ `capture_enabled/set_capture_enabled`（KV `pref.memory_capture`，默认关）+ `extract_and_store(...)`（一次性非流式 LLM 抽取「关于用户、长期有效」的事实，容错解析 JSON 数组、每轮≤3、去重入库）。
  - 新增 `backend/routers/memory.py`：`GET/POST/DELETE/{id}/POST clear/PUT enabled`；`main.py` 注册。
  - `backend/agent/runtime.py`：注入 `memory.build_memory_prompt(user.id)`（个性化之后，全模式）；成功完成且有实质回复且开启时，在助手消息持久化后跑 `extract_and_store`（复用已解析模型凭据），best-effort try/except，失败不影响回复；错误路径提前 return 不抽取。
  - 前端 `src/lib/{types,api}.ts`：`MemoryItem/MemoryData` + `memory/addMemory/deleteMemory/clearMemory/setMemoryEnabled`。
  - `src/components/settings/SettingsModal.tsx`：`MemoryPanel`——生成对话记忆开关 + 手动添加行 + 记忆列表（内容/来源药丸/删除）+ 清空；替掉占位。
  - `src/styles/app.css`：`set-switch*/set-memadd/set-memlist/set-mem*` 样式（token 化，暗色安全）。
  - **设计**：抽取默认**关**（local-first 尊重用户 API 花费，用户显式开启）；已存记忆**始终注入**（记忆的用途），开关只管「是否从对话自动抽取」。「从其他 AI 导入」无真实来源，未做（不伪造）。
- 验证：
  - `py_compile` 五个后端文件过；`tsc --noEmit` 过。
  - 后端重启后 `GET /api/memory` 正常。
  - **真抽取**：开启 → 陈述个人事实的对话（ask）→ `user_memories` 出现 3 条「用户是前端工程师 / 主力 Vue / 名叫小奇」（第 4 条被每轮上限截掉，符合预期）。
  - **真注入生效**：全新会话问「我主力用什么前端框架」（不复述）→ 回复含 `Vue`（从注入记忆答出）。
  - 手动添加成功、重复添加 400、删除成功；CDP 截图**明暗双主题**记忆 panel 渲染无坑（开关 on、3 卡、来源药丸）。
  - 测试后**已关抽取 + 清空记忆**，回到纯净默认态，不残留影响用户。
- commit：feat(WB-146/147/148) 32032bf。

## 审查修复（2026-07-14 复盘）

- **对话抽取阻塞 done 事件 + 无超时**（P1）：`extract_and_store` 原在 `yield done` 之前 `await`，
  开启抽取后每轮要等一次额外 LLM 往返前端才收到 done（UI 卡「运行中」）；且 stream_chat read 超时为 None，
  抽取端点卡死会让该 SSE 永不结束。修：抽取移到 `yield events.done()` **之后**，并用 `asyncio.wait_for(timeout=30)` 兜底。
  实测：done 先到（本轮正常结束），之后仍成功抽取「我最喜欢的编程语言是 Rust」。
- **记忆表无插入上限**（P2）：`_MEMORY_MAX=200` 只在读取生效，`add_memory` 不裁剪 → 行数无界增长、
  去重 SELECT 全表扫描、超 200 的旧记忆静默失效仍占库。修：`add_memory` 插入后裁到最近 `_MEMORY_MAX` 条
  （仿 audit）。临时库 _MEMORY_MAX=3 测：插 5 条只留最近 3 条。
