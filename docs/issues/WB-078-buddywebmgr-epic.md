---
id: WB-078
title: BuddyWebMgr —— Hub 控制台升级为完整 Web 管理门户（总纲/epic）
severity: P1
area: frontend
status: open
origin: 用户诉求 2026-07-08
files:
  - docs/buddywebmgr-管理门户设计.md
  - hub/web/console.html
created: 2026-07-08
---

## 问题

Hub 的 web 控制台（`hub/web/console.html`，262 行）只覆盖控制平面一小角：项目仅 成员/邀请/讨论/在线/时间线，
专家/技能/连接器只有裸 JSON「目录 Admin」，SkillHub 无 UI。用户要求把它升级为完整 Web 管理门户并更名 **BuddyWebMgr**。

## 触发场景

用户检查 Hub 站点功能后提四点：项目管理与 App 不一致；技能/连接器/专家·专家团要有正经管理；SkillHub 要有 UI；更名 BuddyWebMgr。

## 影响

P1：门户是团队用 WorkBuddy 的管理入口，当前能力缺口大。

## 建议修法

见设计文档 [`docs/buddywebmgr-管理门户设计.md`](../buddywebmgr-管理门户设计.md)。定位=**管理控制台**（非 App Web 版）；
硬约束：执行/资产 local-first 进不了 Web、凭据绝不上云。拆分：

- **WB-079** 品牌更名 + 导航重构（骨架）
- **WB-080** 项目管理面 —— 配置编辑（指令 + 连接器/专家/技能 picker）
- **WB-082** 目录运营中心框架 + 专家/专家团 CRUD
- **WB-083** 目录运营中心 —— 连接器 CRUD
- **WB-084** 目录运营中心 —— 技能 + SkillHub
- **WB-081** 团队计划/任务 —— Hub work_items + 同步 + 看板（最重，殿后）

建议顺序：079 → 080 → 082/083/084 → 081。

## 验证

各子任务分别验证；整体：门户更名 BuddyWebMgr，项目可编辑配置，目录三类可视化 CRUD，SkillHub 可浏览/搜索。
