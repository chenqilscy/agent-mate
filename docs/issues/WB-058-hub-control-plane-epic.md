---
id: WB-058
title: WorkBuddy Hub —— local-first 执行 + 云端控制平面重构（总纲/epic）
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - docs/workbuddy-hub-架构设计.md
  - backend/agent/experts.py:9
  - backend/agent/mcp_client.py:70
  - src/data/catalog.ts:1
  - backend/auth/deps.py:30
created: 2026-07-07
---

## 问题

两个结构性问题，来自用户反馈：

1. **能力定义半硬编码**（#1）：专家/技能/连接器的「定义」散在代码里，无法集中管理、运营、下发。
   - 内置专家人格 13 条 [experts.py:9](../../backend/agent/experts.py#L9)（`EXPERTS` 字典，注入系统提示、真生效）
   - 连接器启动注册表 6 个 [mcp_client.py:70](../../backend/agent/mcp_client.py#L70)（`CONNECTORS`，真接入 MCP）
   - 纯静态橱窗目录 [src/data/catalog.ts](../../src/data/catalog.ts)（`EXP_GRID`/`EXP_TEAMS`/`SK_GRID`/`SKILLHUB_*`/`CONNS`/`CONN_META`/模板/灵感，多为展示卡未接真实能力）
2. **协作撑不起团队**（#2）：产品是纯 local-first，后端跑用户本机；M7「协作」靠「共享后端即 Hub」——多用户其实都指向某一台机器的后端，身份/项目/成员各躺一份本机 SQLite，无中心权威源。靠一台个人机在线才能协作，谈不上真正多人/多设备/跨机协作。

## 触发场景

- #1：运营方/团队管理员想新增或调整一个专家人格 / 连接器 / 技能卡，只能改代码重新发版，无法在运行时或管理端维护。
- #2：两名队友要协作同一个项目，必须其中一人的机器常开、另一人连过去；换机、离线、成员管理都没有可靠的中心承载。

## 影响

P1（方向级）：这是产品身份级重构（local-first → 「本地执行 + 云端控制平面」），跨多个里程碑。
不先对齐架构与数据/协议边界就动手，极易大改中途返工。本 issue 作为**总纲**：锚定
[Hub 架构设计文档](../workbuddy-hub-架构设计.md)，把工作拆成可独立交付的阶段，逐条落地。

## 建议修法

按 [架构设计文档](../workbuddy-hub-架构设计.md) 分阶段推进（每阶段一条子 issue）：

| 阶段 | 内容 | Issue |
|---|---|---|
| P0-a | 目录「真定义」入库（内置人格 + 连接器注册表 → 库，运行时改读库） | [WB-059](WB-059-catalog-definitions-to-db.md) |
| P0-b | 橱窗目录入库（`catalog.ts` 静态卡 → 库 + API，前端改从接口取） | [WB-060](WB-060-catalog-showcase-to-db.md) |
| P1 | Hub 服务骨架（账号/组织/项目/成员/邀请权威源 + 鉴权签发） | [WB-061](WB-061-hub-service-skeleton.md) |
| P2 | 本地 ⇄ Hub 同步协议（下行拉取 + 上行 outbox 回传 + 增量） | [WB-062](WB-062-local-hub-sync-protocol.md) |
| P3 | 迁移与 local-first 回退（存量导入、目录权威切 Hub、离线回退） | [WB-063](WB-063-hub-migration-and-local-fallback.md) |

关键边界（铁律对齐）：LLM 凭据与沙箱工作区文件**永不上云**；任何 Hub 不可用场景都必须**降级为本地可用**。

## 验证

- 总纲 issue 的「完成」= 全部子 issue（WB-059～063）关闭，且各自「验证」小节通过。
- 阶段可增量交付：P0（WB-059/060）先在本地库跑通、独立验证，不依赖 Hub 上线。
