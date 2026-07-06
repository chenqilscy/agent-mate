---
id: WB-032
title: 侧栏「任务/空间」列表会话多时不滚动，超出部分被挤压/裁掉
severity: P2
area: ui
status: fixed
origin: 🏚 迁移遗留
files:
  - src/components/layout/Sidebar.tsx:259
  - src/styles/app.css:28
  - src/styles/app.css:51
  - src/styles/app.css:62
created: 2026-07-06
---

## 问题

`.sidebar` 是一个高度受限的 flex 列（`.win` height:100vh → `.shell` flex:1 min-height:0 → `.sidebar` flex 列），
其子项顺序为 `.sb-head` / `.sb-search` / `.nav` / 「任务」`.sb-sec`+`.sb-list` / 「空间」`.sb-sec`+`.sb-list` / `.sb-flex`(flex:1 占位) / `.sb-foot`。

两个 `.sb-list`（`src/styles/app.css:51`）都**没有 `overflow-y` 也没有可滚动的高度约束**。
原型 `docs/workbuddy-v2.html` 只有 2 个任务 + 3 个空间，用 `.sb-flex`(flex:1) 占位把 `.sb-foot` 顶到底部就够了，从没预期会话很多。
真实应用里任务累积到 20+ 条后，列表总高超过侧栏可用高度：由于 flex 子项默认 `flex-shrink:1` 且未设 `overflow`，
列表被挤压、超出部分被裁掉，且没有任何滚动条 —— 用户无法看到/点击靠下的历史会话。

## 触发场景

1. 在助理里累积较多 ad-hoc 会话（截图中「任务 (23)」）。
2. 侧栏任务列表把可视区占满后，靠下的会话被裁掉，滚动鼠标滚轮无任何滚动效果。
3. 同理「空间」项目较多、或某项目展开较多执行时也无法滚动。

## 影响

P2：功能可达性受损 —— 历史会话/项目一旦超过一屏就点不到，只能靠搜索绕过。
不涉及数据正确性，故非 P1；但对多会话用户是高频可见的体验缺陷。

## 建议修法

把「任务」+「空间」两段（各自的 `.sb-sec` + `.sb-list`）一起包进一个滚动容器，让它吃掉 `.sb-flex` 原来占的弹性空间并在溢出时滚动：

- `Sidebar.tsx`：用一个 `<div className="sb-scroll">` 包住从「任务」`.sb-sec` 到「空间」块结束的区域；移除原 `.sb-flex` 占位（滚动容器自身 `flex:1` 已把 `.sb-foot` 顶到底部）。
- `app.css`：新增 `.sb-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; }`（`min-height:0` 是 flex 子项能真正收缩并滚动的关键）。可给一个细窄滚动条样式，明暗主题都用 `var(--border)` 一类会随主题翻转的 token，勿写死浅色。
- 内容未超高时视觉零变化（容器只是接替 `.sb-flex` 填充空间），符合视觉零重设计铁律。

## 验证

- `npx tsc --noEmit` 通过。
- Playwright 实测：构造 20+ 会话，确认任务列表出现滚动条、可滚动到底部并点到最后一条；「空间」多项目/多执行时同样可滚。
- 会话较少（未超高）时，侧栏外观与之前一致，`.sb-foot` 仍贴底。
- 明暗双主题都看一眼滚动条颜色不突兀。
- ≤900px 抽屉态下侧栏仍能正常滚动。

## 处理记录（2026-07-06）

- 改动：
  - `src/components/layout/Sidebar.tsx`：把「任务」`.sb-sec`+`.sb-list` 与「空间」`.sb-sec`+`.sb-list` 两段一起包进一个 `<div className="sb-scroll">`，并移除原 `<div className="sb-flex" />` 占位（滚动容器自身接替弹性空间把 `.sb-foot` 顶到底）。
  - `src/styles/app.css`：把不再引用的 `.sb-flex { flex:1 }` 替换为 `.sb-scroll { flex:1 1 auto; min-height:0; overflow-y:auto; ... }`，并加细窄滚动条样式（`::-webkit-scrollbar` + `scrollbar-color`，thumb 用 `var(--border)`/`var(--text-3)`，随明暗主题翻转）。
- 验证（Playwright，1200×700，23 会话/27 行）：
  - `.sb-scroll` 计算样式 `overflow-y:auto`、`flex:1 1 auto`、`min-height:0`；scrollHeight 940 > clientHeight 352，`scrollTop` 可从 0 滚到底 588。
  - 滚到底可见任务列表尾部 + 「空间(4)」全部项目；`.sb-foot` 始终贴底（footBottom 692 ≤ 窗口 700）。
  - 暗色：`body.dark` 下 `scrollbar-color` 由浅 border 翻为 `rgb(52,58,66)`，无深底深字/突兀问题；`.sb-foot` 仍贴底。
  - ≤900px 抽屉态（800×700，`.sidebar position:absolute` 定高）：`.sb-scroll` 仍可滚（940 > 352，滚到 588）。
  - `npx tsc --noEmit` 通过。
- commit：（待提交）
