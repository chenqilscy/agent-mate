---
id: WB-084
title: 目录运营中心 —— 技能 + SkillHub（浏览/搜索/上架/手动同步）
severity: P2
area: fullstack
status: fixed
origin: WB-078 epic
files:
  - hub/web/console.html
  - hub/routers/catalog.py
created: 2026-07-08
---

## 问题

技能目录只能裸 JSON 编辑；SkillHub 后端已在定时镜像 369 技能（WB-069）+ 有搜索代理，但门户完全没有 UI。

## 触发场景

平台管理员想浏览 SkillHub 镜像、搜索技能、把某些技能上架为精选、或手动触发一次同步 —— 门户里都没有。

## 影响

P2：目录运营中心第三块；把已就绪的 SkillHub 后端接到门户。

## 建议修法

在 WB-082 框架上加：
- **技能**（`SK_GRID`）：icon / 名称 / 简介 / 分类（`SK_CATS`）结构化 CRUD。
- **SkillHub 浏览**：Hub 镜像目录（`replace_skillhub_mirror` 存的行 / `SKILLHUB_*`），分类过滤。
- **搜索**：`GET /catalog/skills/search`（CLI 代理，不可用→空+`cli:false` 提示）。
- **上架/精选**：把镜像技能标进 `SKILLHUB_FEATURED` 供客户端首页展示。
- **手动同步**：`POST /catalog/skills/sync` 按钮 + 上次同步条数/分类统计。

## 验证

浏览镜像目录/分类过滤/搜索有结果；标记精选→`SKILLHUB_FEATURED` 更新→客户端可见；手动同步返回统计；CLI 不可用时优雅降级。

## 处理记录（2026-07-08）

`console.html` 目录运营中心加两 tab：
- **技能**（`skillsCat`）：SK_GRID 三元组 `[icon,name,desc]` CRUD（同框架，编辑/停用/删除）。
- **SkillHub**（`skillhubCat`）：浏览镜像（category `skill`，369 条 rich 对象）+ 分类过滤（`skill-category` taxonomy 12 类）+ 实时搜索（`GET /catalog/skills/search`，CLI 代理，不可用→提示回退）+ 加入/取消精选（写/删 `SKILLHUB_FEATURED`，按 slug 判态）+ 手动同步按钮（`POST /catalog/skills/sync`，接已就绪 WB-069 后端）。
后端未改（复用 WB-082 的 `?all=true` + WB-069 的 sync/search 端点）。
**注**：镜像浏览/搜索 App 已由 WB-070 消费；`SKILLHUB_FEATURED` 精选列的 App 首页消费若形态不同属显示映射后续（同连接器/persona）。
**验证**：Playwright alice(admin)→SkillHub：浏览显 369 技能 + 12 分类 chip；「股票」搜索得 30 条 CLI 结果；ppt「加入精选」→`GET SKILLHUB_FEATURED` 得 slug=ppt、UI「1 个已精选/取消精选」；技能 tab 建「门户测试技能」→`GET SK_GRID` 得正确三元组。手动同步按钮在位（未点以免触发慢速 CLI 全量重取；端点 WB-069 已验）。
