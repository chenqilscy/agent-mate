---
id: WB-145
title: GLM 知识库 Phase D —— Manager console 知识库橱窗 + 目录管理
severity: P2
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - hub/web/console.html
created: 2026-07-14
---

## 问题

Manager console 缺「知识库」目录区——需要策展知识库模板（橱窗 + 目录管理），下发给 App。

## 建议修法

- **零 Schema 改动**：`hub/db.py` 的 `catalog_items` 已支持任意 `category`（`db.py:125`），新 category `knowledge` 直接落；CRUD 走现成 `hub/routers/catalog.py`（平台管理员 gated）。
- **`hub/web/console.html`**：仿 WB-101 连接器 gallery（`cg-` 前缀）新增「知识库」区，用新 `kb-` 前缀（同文件并发防撞）：
  - 「目录」组 nav 加 `nvItem("catalog","知识库","knowledge")`（`:341`）；`catalogView(m)`（`:1116`）加 `knowledge` 分支。
  - 子切换「浏览橱窗 | 目录管理」（`KBSUB`，仿 `CONNSUB`）：橱窗 = 富卡片，管理 = 增改删排序。
  - 模板卡 `data` 形状：`{key,name,desc,icon,embedding_id,contextual,knowledge_type,doc_types[],tags[]}`。
- **下发**：`backend/hub_client.py` 的 `list_catalog(token,"knowledge")` 零改动即可 pull；App `catalogStore` 叠加。

## 验证

隔离 Hub :8100，admin 登录；目录管理增模板卡 → 浏览橱窗可见富卡片 → App pull 后 KnowledgeView 橱窗出现、可「按模板建库」。Playwright 明暗双主题（MCP 浏览器被占则 CDP 自截图）。

## 处理记录（2026-07-14）

- 改动：`hub/web/console.html`——「目录」组 nav 加 `nvItem("catalog","知识库","knowledge")`；CAT_TITLES/catalogView 分发加 knowledge；新增 `knowledgeCat`（子切换 gallery|manage，KBSUB 全局）/`knowledgeGallery`（复用 cg-* 橱窗富卡片+搜索）/`knowledgeDetail`（只读详情+编辑跳管理）/`knowledgeManage`（模板 CRUD 表单：图标/名称/简介/向量模型/knowledge_type/sentence_size/上下文增强/文档类型/标签/排序）。category=`KB_TPLS`，走现成通用 `catalog_items` 表 + `hub/routers/catalog.py` CRUD（零 schema 改动）。
- 验证：node vm 语法检查 console.html script 块无错。**隔离 Hub :8113 + scratch DB + CDP 自截图**（MCP 浏览器被并发占用）：admin 建 KB_TPLS 模板「人事知识库」→ `GET /api/catalog/KB_TPLS?all=true` 与 `/api/catalog`（App 下发形态）均含之 → console 橱窗渲染出富卡片（👔+上下文增强徽章）、管理页渲染出完整表单+列表项（编辑/停用/删除）。下发链路复用 `showcase_all()` 的 `downlink_by_category()` 通用合并，App catalogStore 自动认 KB_TPLS，无需 backend 映射。
- commit：待提交（WB-141 组）。
