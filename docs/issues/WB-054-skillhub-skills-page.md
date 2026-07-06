---
id: WB-054
title: SkillHub 技能页落地（精选/商店网格+下载星标/分类过滤/安装·关闭·编辑·卸载）
severity: P2
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/views/ExpertsView.tsx
  - src/data/catalog.ts:375
  - src/stores/skillStore.ts
  - src/stores/loadoutStore.ts:35
  - src/components/composer/Composer.tsx:98
  - src/styles/app.css
  - src/styles/tokens.css:63
created: 2026-07-07
---

## 问题

「技能」页的 SkillHub 只是占位：`SkillsPane` 里「推荐 / SkillHub / 套件」是三个静态非功能 `.cat`，
没有精选技能、没有商店网格、没有下载/星标、没有分类过滤、没有已安装管理（关闭/编辑/卸载），
也没有 skillhub.cn 入口。参考图（三张截图）要求的 SkillHub 商店体验整体未实现。

## 触发场景

进入「专家·技能·连接器」→「技能」tab：只看到 `为你推荐` + 一排不可点的分类，
点「SkillHub」/「套件」无反应；已安装技能的「⋯」只弹 toast「技能管理 · X」。

## 影响

P2：核心导购/管理页面缺失，和参考设计差距大；纯前端目录页，不涉及数据安全。

## 建议修法

- 目录数据进 `catalog.ts`：`SKILLHUB_FEATURED / SKILLHUB_CATS / SKILLHUB_GRID / SKILLHUB_KITS`
  （静态产品目录，同 `SK_GRID/CONNS`），`SK_GRID` 补 `skill-creator`。
- 已安装/已关闭状态用 `skillStore`（Zustand + localStorage 真持久化，种子取内置 `INSTALLED`）；
  后端无技能安装接口，先客户端持久化（真正挂载会话仍走 `loadoutStore`）。后端接入见 [[WB-055]]。
- `SkillsPane` 重写：精选技能（换一换轮换）→ 推荐/SkillHub/套件 切换 → SkillHub 视图
  （分类过滤 + skillhub.cn 外链 + 综合评分排序 + 带 ↓下载/★星标 的网格卡）。
- 卡片安装态：未装显示「＋」安装；已装显示「✓」+「⋯」菜单（关闭 / 编辑 / 卸载）。
- 顶栏「技能」tab 增「我安装的 N」（计数随安装联动）+「＋ 添加技能」；「我安装的」进已安装管理页。
- 「编辑技能」：`loadoutStore.summonSkills(['skill-creator'])` + `setDraft('请帮我编辑 X 这个 skill')`，
  回首页 composer 消费草稿（Composer 挂载时读取一次 draft）。
- 视觉零重设计：新卡片类只用既有 token（`--border/--chip/--brand-soft/--shadow-sm` 等），
  白底卡与 `.hc-more`/`.card-menu` 同步进 `tokens.css` 的 `body.dark` 覆盖。

## 验证

- `npx tsc --noEmit` 过；`npx vite build` 过。
- 明暗双主题各看一遍：精选卡、网格卡、⋯ 菜单、我安装的页不出现白底白字/深底深字。
- 安装一个技能 → 顶栏计数 +1、卡片翻成 ✓+⋯；关闭 → 标「已关闭」；卸载 → 计数 -1；
  编辑 → 回首页、composer 挂 skill-creator 且预填「请帮我编辑 X 这个 skill」；刷新后已装状态仍在。
