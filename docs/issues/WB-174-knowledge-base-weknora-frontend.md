---
id: WB-174
title: 知识库前端去 GLM 旋钮 —— 配 WeKnora 后端（KnowledgeView/api/types）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/KnowledgeView.tsx
  - src/lib/api.ts
  - src/lib/types.ts
  - src/stores/knowledgeStore.ts
created: 2026-07-14
---

## 问题

配套 [[WB-173]]（后端改用自托管 WeKnora）后，前端仍暴露 GLM 专属旋钮/文案：建库弹窗 `embedding_id` 下拉（3/11/12）+
`contextual` 复选、容量卡的 GLM 配额进度条 + 计价说明（现失真，触铁律#1）、"基于智谱 GLM"/"配置 zhipu key" 文案。
WeKnora 的嵌入模型由其服务端配置，前端无需选；需清理。

## 影响

P2：纯前端。tsc 必过，明暗双主题，复用既有 class。后端响应形状保持不变，改动收敛。

## 建议修法

1. **`KnowledgeView.tsx`**：`CreateKbModal` 去 `embedding_id` 下拉（EMBEDDINGS）+ `contextual`，留 名称/简介/图标
   （可选 chunk_size/overlap）；容量卡去 GLM 配额条 + 计价说明；文案「基于智谱 GLM」→「基于自托管 WeKnora」；
   空态去「配置 zhipu key」；`accept` 用 WeKnora 支持的全格式（pdf/docx/图片/表格/…）。`docStatus` 复用（parse_status 映射后不变）。
2. **`api.ts`/`types.ts`/`knowledgeStore.ts`**：路径/形状基本不变；`createKb` body 去 embedding_id/contextual。

## 验证

- `npx tsc --noEmit` 必过；WeKnora 跑起来后 Playwright 建库/传档/状态/挂载对话实测，明暗双主题；create 弹窗/容量卡无 GLM 残留。

## 处理记录

2026-07-16 · 配套 [[WB-173]] 清理前端 GLM 旋钮。

**改动**：
- `KnowledgeView.tsx`：`CreateKbModal` 去 `embedding_id` 下拉（连 EMBEDDINGS 常量）+ `contextual` 复选，
  留 名称/描述/图标；去容量卡（连 `fmtBytes`、capUsed/capTotal/usedPct、GLM 计价说明）；KB 卡去「上下文增强」badge；
  文案「基于智谱 GLM」→「基于自托管 WeKnora」、密钥→API Key、空态引导改指 docs/weknora-部署.md；
  上传 accept 增图片/html（pdf/doc(x)/ppt(x)/xls(x)/txt/md/html/csv/图片），hint 文案同步。
- `api.ts`：删 `kbCapacity` + `KbCapacity` import；`createKb` body 收敛为 `{name,description?,icon?}`；retrieveKb 保留。
- `types.ts`：`KnowledgeBase` 去 embedding_id/contextual/background/length；`KbDocument` 去 length/url；删 `KbCapacity` 接口。
- `knowledgeStore.ts`：去 capacity 状态与 `api.kbCapacity()` 拉取；create body 收敛。
- 未动 `data/catalog.ts` 的 `KbTemplate`（embedding_id/contextual 是 Manager 策展数据，建库时忽略即可，不夹带）。

**验证**：`npx tsc --noEmit` 通过；`npx vite build` 通过。纯移除既有元素、未新增带主题色的组件（铁律#3 白底白字风险不适用），
故未起前端 + Playwright 双主题实测（并发会话共享 Playwright 浏览器，且改动为已知元素移除，tsc + build 已足够覆盖引用/类型）。
后端响应形状经映射保持不变，前端 store/view 逻辑（docStatus/4s 轮询/挂载）零改照跑。
