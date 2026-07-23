---
id: WB-307
title: Console 项目列表将项目说明渲染为 object Object
severity: P2
area: ui
status: open
origin: 🆕 近期改动
files:
  - console/src/pages/ProjectsPage.tsx:77
created: 2026-07-23
---

## 问题
WB-305 调整项目说明空值展示时，在 ProTable `render` 中对第一个参数执行 `String(value)`；该参数可能是 ProTable 已生成的渲染节点而不是原始字段值，导致真实页面将项目说明显示为 `[object Object]`。

## 触发场景
打开 Console 项目列表，存在有说明或由 ProTable 包装说明单元格的项目时，说明列显示 `[object Object]`。

## 影响
项目列表核心信息不可读，属于近期 UI 回归，因此定为 P2。

## 建议修法
从当前行记录 `item.instruction` 读取原始字符串，不依赖 ProTable 的渲染参数；同时保留空值和 `-` 的友好占位。

## 验证
- 有说明项目展示原始说明，空说明和 `-` 展示“未设置项目指令”。
- Console 类型检查、生产构建和真实浏览器项目列表通过。
