---
id: WB-144
title: GLM 知识库 Phase C —— App 前端知识库管理 + loadout 选择器
severity: P1
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/stores/knowledgeStore.ts
  - src/views/KnowledgeView.tsx
  - src/stores/loadoutStore.ts
  - src/components/layout/Sidebar.tsx
created: 2026-07-14
---

## 问题

用户需要在 App 里建库/传档/管理知识库，并在会话中挂载。

## 建议修法

- **`src/stores/knowledgeStore.ts`**：`list/create/upload/listDocs/deleteDoc/retrieve/capacity`，走本地 `/api/knowledge`（local-first）。
- **`src/views/KnowledgeView.tsx`**：我的知识库列表 + 建库（名称/embedding/上下文增强/图标）+ 传文件（拖拽，显示 `embedding_stat` 向量化进度）+ 文档列表/删除 + 用量条 + 计价提示；顶部从 Manager 下发的知识库模板橱窗一键「按模板建库」。复用 `ExpertsView.tsx` 橱窗样式与 token（视觉零重设计）。
- **Composer ＋ 菜单**：仿 connectors 在 `loadoutStore.ts` 加 `knowledgeIds`，发送并入 `POST /api/chat` 的 `knowledge_ids`。
- **Sidebar**：加「知识库」入口。

## 验证

`npx tsc --noEmit`；Playwright 明暗双主题实测建库/传档/进度/用量/删除；Composer 选知识库发起对话。

## 处理记录（2026-07-14）

- 改动：
  - 新增 `src/stores/knowledgeStore.ts`（list/create/remove/listDocs/uploadDoc/deleteDoc + capacity，local-first）。
  - 新增 `src/views/KnowledgeView.tsx`：列表/详情双态 + 建库弹窗（名称/描述/embedding/图标/上下文增强，复用 np-* 弹窗）+ 上传（拖拽/选择，`embedding_stat` 向量化进度轮询）+ 文档删除 + 用量条 + 计价提示 + 「从模板新建」（消费 catalog KB_TPLS）；复用 scard/card-grid/ec-tag 等既有 class。
  - `src/lib/api.ts` 加 knowledge REST 块（uploadKbDoc 原始 body 仿 uploadFile 带 Bearer）；`src/lib/types.ts` 加 KnowledgeBase/KbDocument/KbCapacity/KbRetrieveHit；`src/data/catalog.ts` 加 KbTemplate + KB_TPLS 内置模板；`catalogStore.ts` 认 KB_TPLS 键。
  - loadout：`loadoutStore.ts` 加 knowledgeIds + kb kind；`sse.ts`/`chatStore.ts` 透传 `knowledge_ids`；`Composer.tsx`/`PlusMenu.tsx` 加知识库 chips+picker 入口；`NewProjectModal.PickerOverlay` 加 kb 分支（动态读 knowledgeStore 按 id 切换）。
  - `src/lib/types.ts` ViewId 加 'knowledge'；`App.tsx` 加 case；`Sidebar.tsx` 更多菜单「ima知识库」死占位换成真「知识库」入口 + activeNav。
- 验证：`npx tsc --noEmit` 过、`npx vite build` 过。**CDP 实截（MCP 浏览器被并发会话占用，退回独立 headless edge + Node WebSocket 走 CDP）**：App 知识库视图渲染出真 GLM 用量「0 / 1.00 GB」+ 4 张模板卡；Composer ＋ 菜单出现「知识库」项。
- commit：待提交（WB-141 组）。
