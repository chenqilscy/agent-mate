---
id: WB-141
title: GLM 知识库 RAG 接入（总纲/epic）—— 本地 backend 执行 + Manager 目录管理
severity: P1
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/glm_kb.py
  - backend/routers/knowledge.py
  - backend/agent/tools.py
  - backend/agent/runtime.py
  - src/views/KnowledgeView.tsx
  - hub/web/console.html
created: 2026-07-14
---

## 问题

AgentMate 缺少 RAG 能力——agent 无法基于用户上传的资料库检索作答。GLM（智谱/bigmodel）提供
一整套知识库 REST API（建库/传文档/文档管理/文本检索/全模态检索/上下文增强），可接入为真正的
知识库能力。用户诉求：「参考 GLM 知识库，在 AgentMate Manager 中实现」。

**核心约束**：GLM 知识库所有 API 都要智谱 API Key，而铁律#4 规定 LLM Key 只存本地 backend
（按 owner 存 DB）、绝不进 Hub/Manager。故功能天然分两面（呼应 Hub「云端控制平面 + local-first 执行」）：
- 执行面 = 本地 backend（有 zhipu key）：真·建库/传档/检索 + 检索接进 agent 工具循环。
- 管理面 = Manager console：知识库橱窗 + 目录管理（策展模板，沿用 WB-100/101/102 gallery 模式），下发给 App；不碰 key。

## 触发场景

用户在 App 建一个 GLM 知识库、上传若干文档，在会话中挂载它并提问资料性问题 → agent 应调
`knowledge_retrieve` 真检索 GLM 知识库并引用命中内容作答（真 SSE 事件，非脚本）。

## 影响

补齐 RAG 这一核心能力缺口；P1。范围较大，拆四个子任务分阶段落地。

## 建议修法

方案与 API 细节见 `C:\Users\chenq\.claude\plans\proud-wibbling-key.md`。分四子任务：
- **WB-142（Phase A · backend）**：`agent/glm_kb.py` httpx 客户端 + `routers/knowledge.py`（建库/传档/文档管理/检索/全模态/用量），key 走 `db.get_provider_key(owner_id,"zhipu")`。
- **WB-143（Phase B · agent 工具循环）**：`knowledge_retrieve` 工具 + contextvar 注入 + `ChatBody.knowledge_ids` loadout 透传。
- **WB-144（Phase C · App 前端）**：`KnowledgeView` + `knowledgeStore` + Composer loadout 选择器 + Sidebar 入口。
- **WB-145（Phase D · Manager console）**：知识库橱窗 + 目录管理（`kb-` 前缀）+ `catalog_items` 新 category `knowledge` 下发。

## 验证

见各子任务；端到端：backend 真调建库/传档/检索通 → 会话挂载 KB 出现 `knowledge_retrieve` 事件 →
Manager 目录管理增模板卡、App 橱窗可见并「按模板建库」。硬依赖：DB 里配一枚真智谱 Key。

## 处理记录（2026-07-14）

四子任务 WB-142~145 全部落地并真机实测通过（详见各子任务处理记录）：

- **WB-142 (backend 引擎)**：`agent/glm_kb.py` + `routers/knowledge.py`，真机建库→传档→向量化→检索全通；修掉 GLM 动态解析「文档损坏」坑（默认 knowledge_type=5）。
- **WB-143 (agent 工具循环)**：`knowledge_retrieve` 工具 + loadout 透传；SSE 真出工具事件、答案引用来源（glm-4.7-flash 真跑）。
- **WB-144 (App 前端)**：`KnowledgeView` + `knowledgeStore` + Composer loadout；CDP 实截真 GLM 用量 + 模板橱窗 + ＋菜单入口。
- **WB-145 (Manager console)**：知识库橱窗+目录管理（KB_TPLS category，零 schema）；隔离 Hub CDP 实截 CRUD+橱窗+下发。

**验证手段记录**：MCP 浏览器被并发会话独占，UI 验收退回「独立 headless msedge + Node v24 内置 WebSocket 走 CDP 自截图」（见 memory）。真智谱 Key 已配在本地 backend，端到端真调全部落地；所有测试知识库均已清理。

## 已知取舍 / 后续

- 项目级 KB loadout（`project.knowledge`）未做——本期仅 per-message/session loadout（需改 projects 模型，后置）。
- 全模态检索/上下文增强：backend 已实现（`/retrieve/multimodal`、建库 contextual 开关 + App 建库勾选），全模态图像查询 UI 从简（backend 就绪，前端可后续增强）。
- GLM 原生 `tools:[{type:retrieval}]` 挂载：按范围确认不做（用自研 knowledge_retrieve 工具，跨厂商更通用）。
