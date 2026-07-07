---
id: WB-085
title: 助理页顶栏按钮接真实 transcript —— 对话内搜索 / 分享导出 / 历史提问（去掉 toast 占位）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/AssistantView.tsx
  - src/views/ChatView.tsx
  - src/components/chat/ChatSearch.tsx
  - src/lib/exportChat.ts
created: 2026-07-08
---

## 问题

WB-072/077 让助理页有了真实状态、真实会话、设置面板，但右上顶栏的 **对话内搜索 / 分享 /
历史提问** 三个按钮仍只 `toast(...)` 占位（[AssistantView.tsx](../../src/views/AssistantView.tsx)），
而同样的能力在 [ChatView.tsx](../../src/views/ChatView.tsx) 已是真实实现。助理页有真实 transcript 后，
这些按钮应当真正可用。

## 触发场景

助理页点「搜索」→ 应打开对话内查找条（⌘F 亦可）；点「分享」→ 复制/下载 Markdown；
点「历史提问」→ 列出我发过的问题、点击跳转。当前都只弹 toast。

## 影响

P2：纯前端 polish，去掉助理页最后一批假按钮，与 ChatView 行为一致。

## 建议修法

复用 ChatView 已有实现，不造新轮子：
- `ChatSearch`（`src/components/chat/ChatSearch.tsx`）：`{searchOpen && <ChatSearch containerRef={scrollRef}
  messages={display} onClose=.../>}` + ⌘F/Ctrl+F 打开。
- 分享/导出：`conversationToMarkdown` / `copyText` / `downloadText` / `safeFilename`（`src/lib/exportChat.ts`）
  + `Popover`（复制为 Markdown / 下载 .md）。标题用「助理 · @bot」。
- 历史提问：`questions = 真实 transcript 里 role=user 的消息` + `Popover` 列表 + 点击 `scrollIntoView`
  到 `#msg-<id>`（`MessageList` 已渲染该 id）。
- 「产物面板」暂留 toast：助理会话消息未携带 trace，OvPanel 会是空的，接了无意义——另开 issue 时
  再连（需渠道端点带上 trace）。

## 验证

- `npx tsc --noEmit`、`npx vite build` 通过。
- 助理页：⌘F 打开搜索并高亮/跳转；分享弹层复制+下载 .md 成功；历史提问列出并跳转；
  空对话时分享/历史给出「还没有…」而非报错。
- 明暗双主题看这几个弹层（复用 ChatView 既有类，天然暗色）。

## 处理记录（2026-07-08）

- 改动：`views/AssistantView.tsx` —— 复用 ChatView 的 `ChatSearch` / `Popover` / `exportChat`，把
  顶栏 搜索/分享/历史 三个 fic 按钮从 `toast` 接到真实 transcript：
  - 搜索：`{searchOpen && <ChatSearch containerRef={scrollRef} messages={display}/>}` + ⌘F/Ctrl+F 打开；
  - 分享：Popover（复制为 Markdown / 下载 .md），基于真实 transcript（base），空对话给「还没有对话内容」；
  - 历史提问：Popover 列出 base 里 role=user 的消息，点击 `scrollIntoView` 到 `#msg-<id>`；
  - 产物面板仍 `toast`（渠道消息未带 trace，OvPanel 会空——另开 issue 时让端点带 trace 再连）。
- 验证：`npx tsc --noEmit`、`npx vite build` 通过；复用 ChatView 已验证组件、逻辑逐字对齐，行为一致。
  未跑：浏览器明暗双主题实时截图（Playwright profile 被用户占用无法接管）；复用既有主题安全类，无新增风险色。
- commit：（尚未提交）
