---
id: WB-084
title: 目录运营中心 —— 技能 + SkillHub（浏览/搜索/上架/手动同步）
severity: P2
area: fullstack
status: open
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
