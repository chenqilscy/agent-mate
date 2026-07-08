---
id: WB-092
title: BuddyWebMgr SkillHub 页向真实 SkillHub 站点对齐（发布来源/排序/富卡片）
severity: P3
area: frontend
status: fixed
origin: 用户对比真实 SkillHub 站点
files:
  - hub/web/console.html
created: 2026-07-08
---

## 问题

WB-084 的 SkillHub 页只有 分类 chip + 简卡（名称/分类/★）。用户对比真实 SkillHub 站点，希望对齐：
左侧 **发布来源**（SkillHub/ClawHub）、**排序方式**（推荐精选/下载量/收藏量…）、场景分类，以及更丰富的卡片（图标/下载量/来源）。

## 触发场景

用户并列看 BuddyWebMgr 的 SkillHub 页与 skillhub 真站点，风格/筛选维度差距明显。

## 影响

P3：观感/可用性对齐；不改数据来源。

## 建议修法（只做数据支持得了的，绝不造字段）

镜像数据（category `skill`，369 条）**有**：`source`(clawhub/community/enterprise)、`score`/`downloads`/`installs`/`stars`、
`iconUrl`、`skillhub_category(_name)`、`verified`。据此重排 SkillHub 页为「左筛选 + 右列表」：
- **发布来源**：全部 / SkillHub（source∈{community,enterprise}）/ ClawHub（source=clawhub）。
- **排序方式**：推荐精选(score) / 下载量(downloads) / 收藏量(stars) / 安装量(installs)，降序。
- **场景分类**：沿用 taxonomy 12 类。
- **富卡片**：iconUrl 图标（外链，Hub 同源可加载，broken 时隐藏）+ 名称 + 来源标 + 分类标 + ★收藏 + ⬇下载(万) + 简介 + 加入精选。

**数据缺、诚实不做**：`是否需要 API Key` 筛选、`近期飙升 / 最近上新` 排序——SkillHub CLI 榜单 feed **不提供** per-skill 的 api-key 需求与发布日期（`skillhub_sync` 已 `{**card}` 全量入库，确实没有这两类字段）。

## 验证

SkillHub 页出现发布来源/排序/分类三组筛选 + 富卡片；切来源/排序/分类列表随之变；搜索仍走 CLI 代理；加入精选照常。

## 处理记录（2026-07-08）

`console.html` 重排 `skillhubCat` 为「左筛选面板 + 右富列表」（grid 180px/1fr），贴近真站：
- **发布来源**：全部 / SkillHub（source∈{community,enterprise}）/ ClawHub（source=clawhub）。
- **排序方式**：推荐精选(score) / 下载量(downloads) / 收藏量(stars) / 安装量(installs)，降序。
- **场景分类**：taxonomy 12 类竖排。
- **富卡片**：iconUrl 图标（外链，Hub 同源可加载，broken→隐藏）+ 名称 + 来源标(ClawHub/社区/企业) + 分类标 + ★收藏 + ⬇下载(万) + 简介 + 加入精选。
**数据缺、诚实未做**：`是否需要 API Key` 筛选、`近期飙升/最近上新` 排序——`skillhub_sync` 已 `{**card}` 全量入库，
镜像 369 条里确无 api-key 需求标记与发布日期字段（SkillHub 榜单 feed 不提供），不造字段。
**验证**：Playwright alice(admin)→SkillHub：左栏三组筛选 + 富卡片（图标/ClawHub 来源标/★/⬇万）；
默认「推荐精选」排序 self-improving agent(★4180/⬇95.2万) 居首；点「发布来源=SkillHub」→列表只剩 社区/企业 卡、ClawHub 消失。
