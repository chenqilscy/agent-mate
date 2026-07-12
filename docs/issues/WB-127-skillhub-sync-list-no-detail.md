---
id: WB-127
title: 目录运营中心「SkillHub 同步」列表无查看技能详情入口
severity: P3
area: frontend
status: fixed
origin: 既有实现
files:
  - hub/web/console.html:1644
created: 2026-07-12
---

## 问题

目录运营中心「技能」页第三子视图「SkillHub 同步」（`skillhubCat()`，
[console.html:1603-1649](../../hub/web/console.html#L1603-L1649)）把每条同步技能渲染成
`.list-item`（[console.html:1644-1645](../../hub/web/console.html#L1644-L1645)）：图标 + 名称 +
若干 pill（来源/分类/★/⬇）+ **一行被 `white-space:nowrap` 截断的描述** + 右侧「加入精选 / 取消精选」按钮。

整个 `.list-item` **未绑定点击事件**（只有 `data-feat` 按钮可点），所以对一条同步技能无法
点开看完整信息（description 全文 / 分类 / 统计 / 标签 / 来源链接）。

对比同一「技能」页的另两个子标签：「浏览橱窗」的富卡片有点开的详情弹窗（`sgDetail()`，
[console.html:1570](../../hub/web/console.html#L1570)），但它只渲染已「加入精选」的目录项，
覆盖不到同步列表里全部技能。因此对**未加入精选**的同步技能，目前确实没有地方看全貌。

## 触发场景

登录 Manager 控制台 → 目录运营中心 → 技能 → SkillHub 同步子标签 → 列表里任一技能，
想看它的完整介绍 → 描述被截断成一行、点卡片无反应 → 只能先「加入精选」再切「浏览橱窗」，
或去「高级 JSON」看裸 data，均绕。

## 影响

P3：不阻塞主流程（加入精选/同步都可用），但运营人员挑选技能时看不到全貌，需要绕路。

## 建议修法

复用现成的 `sgDetail(c)` 弹窗（[console.html:1570](../../hub/web/console.html#L1570)，接收技能
data 对象即渲染），给 `.list-item` 加点击打开详情：

- 让每条列表项可点（`sg-click` 光标 + 绑定 onclick），点击调 `sgDetail(it.data)`。
- 阻止「加入精选」按钮的点击冒泡到卡片，避免点按钮也弹详情。
- 纯前端、仅改 `hub/web/console.html` 的 `skillhubCat()` 渲染/接线，无后端改动。

## 验证

- 明暗双主题下：SkillHub 同步列表点任一技能 → 弹出详情弹窗，展示完整描述/分类/★⬇/标签/来源链接；
  点「加入精选」按钮不误触发详情；Esc / 点遮罩 / × 均能关闭。
- 隔离 Hub（:8100 alice/alice123 或 scratchpad DB）实测；无后端改动，`api()` 路径不变。

## 处理记录（2026-07-12）

- 改动：仅 [hub/web/console.html](../../hub/web/console.html) 的 `skillhubCat()` 列表渲染/接线
  （[console.html:1644-1647](../../hub/web/console.html#L1644-L1647)）：
  - 列表项加 `sg-click` 光标 + `data-detail="${i}"` + `title="查看详情"`，标题栏文案补「· 点条目查看详情」；
  - 新增 `[data-detail]` 点击接线 → 复用现成 `sgDetail(shown[i].data)` 弹窗（与浏览橱窗
    [console.html:1567](../../hub/web/console.html#L1567) 同一模式）；
  - 「加入精选」按钮 onclick 加 `e.stopPropagation()`，点按钮不冒泡触发详情。
  - 无后端改动。
- 验证：MCP 浏览器被并发会话占用，改用 node DOM-shim 谐振器（vm 里跑**真·抽取的
  `sgDetail`/`esc`/`shSrc` 等函数** + 复刻的渲染/接线尾段，DB 无关）——10 项断言全过：
  列表含 `data-detail=0`/`sg-click`；点条目开且仅开一个 `sg-overlay`，弹窗含完整描述/分类
  「办公效率」/★109/标签 ppt/来源「社区」；点「加入精选」触发 `stopPropagation` 且不重复开窗。
  先经 `new Function()` 全脚本语法校验通过。
- commit：未提交（待用户指示）。
