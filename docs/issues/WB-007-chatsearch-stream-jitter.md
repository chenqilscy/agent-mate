---
id: WB-007
title: ChatSearch 流式抖动 + 当前高亮陈旧
severity: P1
area: frontend
status: open
origin: 🆕 近期改动
files:
  - src/components/chat/ChatSearch.tsx:61
  - src/components/chat/ChatSearch.tsx:79
  - src/views/ChatView.tsx:42
created: 2026-07-06
---

## 问题
两点：
1. **流式抖动/性能**：重算 effect 依赖 `[query, messages, containerRef]`（`ChatSearch.tsx:61`），流式回复每来一个 token 就整树 `TreeWalker` 重建全部 Range（长对话 O(n)/token）；激活 effect 在 `count` 变化时对当前项 `scrollIntoView({behavior:'smooth'})`，与 `ChatView.tsx:42` 的「钉底部」`useLayoutEffect` 互相抢滚动 → 画面来回抖，大量匹配时卡顿。
2. **当前高亮陈旧**：激活 effect 依赖 `[current, count]`（`:79`）。query 从「ab」(2 个)改为「cd」(仍 2 个)时 `current`/`count` 均未变 → effect 不重跑 → `HL_CUR` 仍画在旧位置，也不滚动到新匹配。

## 触发场景
开着搜索时模型流式输出；或搜同样匹配数的不同词。

## 影响
搜索在真实使用中抖动、当前项定位错乱。

## 建议修法
- 重算做防抖（rAF 或 ~150ms）。
- 仅在**用户显式导航**（Enter / ▲▼）时 `scrollIntoView`；streaming 触发的重算不滚动。
- 激活 effect 依赖加入 `query`（或 ranges 版本号）。

## 验证
边流式边开搜索：不抖、不卡；搜「ab」→改「cd」：当前高亮跳到新匹配并滚动到位。
