---
id: WB-252
title: 助理页被长对话撑高并整体移出视口
severity: P0
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/App.tsx:77
  - src/styles/antd.css:15
  - src/views/AssistantView.tsx:105
created: 2026-07-21
---

## 问题
App 接入 Pro `PageContainer` 后，全高度链遗漏 `.ant-pro-grid-content-children`。助理长对话把中间容器撑到 4128px，`body` 的居中 flex 布局随之把整个 `.shell` 上移约 3160px。

## 触发场景
直接打开 `/assistants`，且选中助理存在较长历史对话时，顶部全局侧栏、助理列表、页签和早期消息全部移出视口，只剩对话底部。

## 影响
P0：助理管理和历史对话入口实际不可用，桌面与 860px 窄屏均可复现。

## 建议修法
补齐 Pro PageContainer 中间节点的 `height/min-height/overflow` 高度链，并确保 `.main`、`.asst` 与 `.chat-col` 在固定视口内收缩，滚动只发生在各自滚动容器。

## 验证
- 1440x1000、860x720 直接打开 `/assistants` 时 `.shell` 与助理页顶部均从 y=0 开始。
- 长对话只滚动 `.chat-scroll`，助理列表、页签和输入框保持可见。
- 明暗主题均正常。

## 处理记录（2026-07-21）
- 改动：补齐 `.ant-pro-grid-content-children` 全高度与 flex 收缩链，限制 `.main` 溢出，并隐藏 Pro PageContainer 空标题生成的 32px `ant-page-header-no-children` 占位。
- 验证：1440×1000 与 860×720 真机浏览器中 `.shell/.main/.asst` 均 `y=0` 且严格等于视口高度；长对话 `scrollHeight=3997` 仅由 `.chat-scroll` 滚动，输入框保持可见；页面无横向溢出。
- 提交：本次 WB-016/WB-252/WB-253/WB-254/WB-256 UI 审查修复提交。
