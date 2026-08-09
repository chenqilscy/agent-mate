---
id: WB-472
title: CompatList 将 loading 属性透传到 DOM 触发 React 控制台告警
severity: P2
area: frontend
status: open
origin: 既有实现
files:
  - src/components/ui/CompatList.tsx:6
  - src/views/WorkspaceContextsView.tsx:58
created: 2026-08-09
---

## 问题

`CompatListProps` 没有声明并消费 `loading`，调用方传入 `loading={false}` 时该属性进入 `...rest`，最终被写到原生 `div`。React 因而报告“Received false for a non-boolean attribute loading”。

## 触发场景

打开 App“项目任务”页 → `WorkspaceContextsView` 使用 `CompatList loading={...}` → 页面正常显示，但浏览器控制台产生 React 属性告警。

## 影响

P2：不阻断页面，但污染浏览器错误日志，使真实 UI 回归难以区分业务错误和组件契约错误；任何继续使用 `CompatList loading` 的页面都会复现。

## 建议修法

- 在 `CompatListProps` 中显式支持并消费 `loading`，不要透传给 DOM。
- 加载中且无数据时渲染诚实的加载状态，保持现有 Ant class 与主题契约。
- 增加静态或组件回归，锁定 `loading` 不进入原生元素。

## 验证

- 打开项目任务页时 DOM 不含 `loading` 属性。
- 浏览器控制台不再出现 non-boolean `loading` 告警。
- `npx tsc --noEmit` 与 App 构建通过。
