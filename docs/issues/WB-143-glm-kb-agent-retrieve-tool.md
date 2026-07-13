---
id: WB-143
title: GLM 知识库 Phase B —— knowledge_retrieve 工具接进 agent 工具循环 + loadout
severity: P1
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/tools.py
  - backend/agent/runtime.py
  - backend/routers/chat.py
created: 2026-07-14
---

## 问题

有了 backend 引擎（WB-142），还要让 agent 在会话中真检索知识库——把 `knowledge_retrieve` 接进工具循环，
按会话 loadout 挂载。

## 建议修法

仿 work-item 工具的 contextvar 注入法（`tools.py:230-244` 的 `_work_ctx`/`set_work_context`）：
- **tools.py**：加 `_kb_ctx` + `set_knowledge_context(owner_id, knowledge_ids)`；加 `knowledge_retrieve` Tool（参数 query，可选 top_k）：读 ctx → `db.get_provider_key` → `glm_kb.retrieve` → 拼命中片段（text+score+doc_name）；`pre` 出 `step tool=knowledge_retrieve`。ctx 空则「未挂载知识库」。
- **runtime.py**：`run_chat(..., knowledge_ids=None)`；`set_knowledge_context(user.id, active_knowledge)`；`active_knowledge=_dedup(proj_knowledge+(knowledge_ids or []))`；非 ask 且非空时把工具加进 `tools_list` + 系统提示提示用法 + loadout 展示行追加「知识库 N 个」。
- **chat.py**：`ChatBody` 加 `knowledge_ids: list[str]=Field(default=[],max_length=50)`；`run_chat(... knowledge_ids=body.knowledge_ids)`。

## 验证

`py_compile`；`POST /api/chat` 带 `knowledge_ids=[kb]` 问资料性问题，SSE 出现 `step tool=knowledge_retrieve` 且答案引用检索内容。

## 处理记录（2026-07-14）

- 改动：
  - `backend/agent/tools.py`：加 `_kb_ctx` contextvar + `set_knowledge_context(owner,knowledge_ids)`；加 `knowledge_retrieve` Tool（延迟 import glm_kb，读 ctx→`db.get_provider_key`→`glm_kb.retrieve`，拼来源/相关度/片段，pre 出 `step tool=knowledge_retrieve`；未挂载/无 key/检索空各有诚实提示）。
  - `backend/agent/runtime.py`：`run_chat(..., knowledge_ids=None)`；`active_knowledge=_dedup(knowledge_ids or [])`；`set_knowledge_context`（ask 模式置空）；非 ask 且非空时把工具加进 tools_list + 系统提示「已挂载知识库」用法段 + loadout 展示行加「知识库 N 个」。
  - `backend/routers/chat.py`：`ChatBody.knowledge_ids`（max 20）+ 透传 run_chat。
- 验证：`py_compile` + 导入冒烟过。**真机端到端全通**：建库+传档+向量化后 `POST /api/chat` 带 `knowledge_ids=[kb]` 问「WorkBuddy 后端框架/端口」，SSE 依次出 `think`（"需要先用 knowledge_retrieve 检索"）→`step {tool:knowledge_retrieve, label:"检索知识库 …"}`→`text`，最终答案精准引用「后端框架 Python FastAPI，默认端口 8000，来源 wb_facts.txt」（默认模型 glm-4.7-flash，真 LLM+真检索，非脚本）。
- commit：待提交（WB-141 组）。
