---
id: WB-082
title: 目录运营中心框架 + 专家/专家团 类型化 CRUD（替裸 JSON）
severity: P2
area: frontend
status: open
origin: WB-078 epic
files:
  - hub/web/console.html
created: 2026-07-08
---

## 问题

专家/专家团在门户只能靠裸 JSON「目录 Admin」增删，无结构化编辑。

## 触发场景

平台管理员想新增/编辑一个内置专家或专家团 —— 现在得手输 category + JSON 元组，易错、不可用。

## 影响

P2：目录运营中心的第一块 + 通用类型化编辑框架。

## 建议修法

- **框架**：目录运营中心页，按类型 tab（专家/专家团/连接器/技能/SkillHub）；每类=卡片列表 + 结构化编辑器 + 启用/停用/排序/删除，写 `catalog_items`（`POST/PATCH/DELETE /catalog`），保留「高级 JSON」兜底。
- **专家**（`EXP_GRID`）：icon / 名称 / 副标题 / 简介 / 标签 / 分类（`EXP_CATS`）/ persona（真定义，可选）。
- **专家团**（`EXP_TEAMS`）：名称 / 图标 / 成员专家清单（引用专家名）。
- 仅平台管理员可写；改动经客户端 pull 下发（WB-066 已就绪）。

## 验证

新增/编辑专家与专家团→列表刷新→`GET /catalog` 数据正确→客户端 pull 后 App 专家页可见；停用/排序/删除生效。
