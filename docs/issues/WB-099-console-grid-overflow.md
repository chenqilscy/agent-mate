---
id: WB-099
title: BuddyWebMgr SkillHub 页横向溢出（CSS grid 1fr 被内容撑破）
severity: P3
area: ui
status: fixed
origin: 用户截图（SkillHub 宽度大于页面）
files:
  - hub/web/console.html
created: 2026-07-09
---

## 问题

SkillHub 页（左筛选 180px + 右列表）出现横向滚动条、整页宽度超出视口。根因：grid 列用 `1fr`（= `minmax(auto,1fr)`），
右列内容（长技能名/描述/多枚 pill）的 **min-content 宽度**把 `1fr` 列撑到超过容器 → 整个 `.main`/`.wrap` 被撑宽。

## 触发场景

目录运营中心 → SkillHub，列表里有长描述/长英文串的卡片 → 页面底部出现横向滚动条。

## 影响

P3：观感/布局 bug；不影响功能。同类隐患也在计划/任务看板（`repeat(4,1fr)`）与 `.grid2`。

## 建议修法

CSS grid 经典修法：`1fr` → `minmax(0,1fr)`，让列可缩到内容 min-content 以下、由卡片内部 `min-width:0`+`ellipsis` 兜住。
- SkillHub：`180px 1fr` → `180px minmax(0,1fr)`。
- 看板：`repeat(4,1fr)` → `repeat(4,minmax(0,1fr))`。
- `.grid2`：`1fr 1fr` → `minmax(0,1fr) minmax(0,1fr)`。

## 验证

SkillHub / 看板 / 各表单 grid 不再横向溢出；窄视口下列内容省略号截断而非撑破页面。
