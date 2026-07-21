---
id: WB-281
title: ChatSearch 无法匹配跨 Markdown 文本节点短语
severity: P3
area: frontend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/components/chat/ChatSearch.tsx:24
created: 2026-07-22
---

## 问题
`collectRanges` 对每个 text node 分别执行 `indexOf`。Markdown 渲染会把加粗、行内代码和链接拆成相邻节点，因此查询横跨这些节点时没有结果。

## 触发场景
回复中存在 `alpha **beta**`，在对话搜索中输入 `alpha beta`，结果显示「无结果」。

## 影响
P3。搜索结果不完整，但不影响消息数据和执行链路。

## 建议修法
在单条 `.msg` 内建立连续文本及节点偏移映射，再把命中区间映射回跨节点 `Range`；消息之间保持边界，避免跨消息误命中。

## 验证
- Chromium DOM 中查询可跨普通文本与 `strong`、`code`、`a` 节点。
- 不把上一条消息末尾与下一条消息开头拼成一个结果。
- `npx tsc --noEmit` 通过。

## 处理记录（2026-07-22）
- 改动：`ChatSearch.collectRanges` 改为按单条 `.msg` 合并文本并保存节点偏移，命中后生成可跨 Markdown 行内元素的 `Range`；消息边界不合并。
- 验证：`npx tsc --noEmit` 通过；真实 Chromium/Vite 页面中 `alpha <strong>beta</strong> <code>gamma</code> <a>delta</a>` 查询得到完整 `alpha beta gamma delta`，相邻消息 `tail`/`head` 查询 `tailhead` 为 0 个结果。
- commit：本提交。
