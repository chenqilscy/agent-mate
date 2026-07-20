---
id: WB-205
title: Skills 页面卡片网格被长内容撑宽并出现横向滚动条
severity: P2
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/styles/app.css:231
  - src/styles/app.css:1403
created: 2026-07-20
---

## 问题

Skills 页在约 960px CSS 视口下出现内容区横向滚动条，向右滚动后左侧卡片会被主栏边界裁切。
浏览器实测 `.card-grid.g4` 的可用宽度为 651px，但 `scrollWidth` 被长技能描述撑到 6000px。
根因是网格列使用 `1fr`（等价于 `minmax(auto, 1fr)`），卡片的最小内容宽度参与轨道计算；
SkillHub 的长英文/URL 文本因此把两列各撑到约 1732px。

## 触发场景

打开 Skills → SkillHub；窗口宽度约 960px 或系统缩放后等效宽度接近该值 → 主内容底部出现横向滚动条。

## 影响

P2。核心浏览页在常见窗口宽度下无法稳定阅读，且水平滚动会让内容被侧栏裁切。

## 建议修法

沿用 WB-099 已验证的网格约束，把通用 `.g2/.g3/.g4` 的 `1fr` 改为
`minmax(0, 1fr)`，并给网格卡片保持 `min-width: 0`，让长内容在卡片内截断/换行而非撑宽页面。

## 验证

- 960px、860px、桌面宽度下 `.hub-body.scrollWidth == clientWidth`；
- SkillHub 与推荐两段均无横向滚动条，卡片内容不越界；
- 浅色、深色主题通过；
- `npx tsc --noEmit`、`npx vite build` 通过。

## 处理记录（2026-07-20）

- 改动：`src/styles/app.css` 将 `.g1/.g2/.g3/.g4` 的网格轨道统一改为
  `minmax(0, 1fr)`，并给 `.card-grid` 直接子项增加 `min-width: 0`；900px 以下的两列规则同步修正。
- 验证：Playwright 在 1280/960/900/860px、浅色/深色、SkillHub/推荐组合下逐一测量，
  `.hub-body`、卡片网格及文档的 `scrollWidth - clientWidth` 全部为 0；专家与连接器页面同宽度回归也为 0。
- 验证：修复前 960px 下网格 `6000 - 651px`，修复后为 `651 - 651px`；页面截图确认长描述在卡片内正常截断。
- 验证：`npx tsc --noEmit`、`npx vite build`、`git diff --check` 通过。
- commit：本提交（WB-205）。
