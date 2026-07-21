---
id: WB-254
title: Console 概览栅格与高级 JSON 窄屏操作不可达
severity: P1
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - console/src/pages/OverviewPage.tsx:43
  - console/src/pages/RawCatalogPage.tsx:27
  - console/src/pages/RawCatalogPage.tsx:32
created: 2026-07-21
---

## 问题
平台管理员概览有 5 张统计卡，每张 `xl=5` 导致总跨度 25/24，第五张单独换行；高级 JSON 在 860px 下使用 900px 固定表格，启用与操作列被横向裁到不可见区域且缺少滚动提示。

## 触发场景
管理员登录 Console 后打开概览；再把视口缩到 860px 打开“高级 JSON”。

## 影响
P1：概览层级失衡；窄屏下核心运营操作不易发现，并且启用 Switch 没有可访问名称。

## 建议修法
让 5 张卡在宽屏使用五等分栅格；窄屏高级 JSON 固定操作列并增加可见的横向滚动提示/滚动条，为每行 Switch 补充带目录身份的 `aria-label`。

## 验证
- 1440px 下 5 张统计卡同一行等宽。
- 860px 下操作列始终可见，表格可横向滚动且有明确提示。
- Switch 可通过可访问名称定位并键盘切换。

## 处理记录（2026-07-21）
- 改动：概览统计区改为五等分 CSS Grid，并提供 2/1 列断点；高级 JSON 启用与操作列固定右侧，增加窄屏横向滚动提示，每行 Switch 提供包含分类的 `aria-label`；重新生成 Server 正式 Console 静态包。
- 验证：正式 `127.0.0.1:8100` 在桌面下 5 卡同一行等宽；860px 下提示可见，固定列位于 x=559–789 的可视区域，操作列 `position: sticky`；Switch 可访问名称为“APP_SKILLS 目录项启用状态”。
- 提交：本次 WB-016/WB-252/WB-253/WB-254/WB-256 UI 审查修复提交。
