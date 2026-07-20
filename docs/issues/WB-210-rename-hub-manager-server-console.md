---
id: WB-210
title: Hub 与 Manager 命名不能准确表达 API 服务和 Web 控制台职责
severity: P1
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/config.py:131
  - backend/server_client.py:1
  - backend/routers/server.py:1
  - server/main.py:1
  - server/web/console.html:6
  - src/stores/serverStore.ts:1
  - README.md:15
created: 2026-07-20
---

## 问题

当前中心 API 服务叫 `AgentMate Hub`，其 Web 管理端叫 `AgentMate Manager`。`Hub` 没有直接表达它是中心 Server/API，`Manager` 又容易被理解成独立服务，而实际上它只是由中心服务托管、同源调用 API 的 Web 控制台。

技术层同时存在 `hub/`、`hub_client.py`、`hub_sync.py`、`HUB_URL`、`hubStore`、`/api/hub/*` 等命名，继续沿用会让产品概念与代码职责长期错位。

## 触发场景

介绍系统组成、配置中心服务地址或排查 App 与中心服务的同步链路时，需要额外解释 Hub/Manager 的关系，代码和部署文档也无法从名称直接判断哪个是 API、哪个是 Web。

## 影响

P1：产品架构命名含混，并已扩散到目录、环境变量、模块、前端 store、代理路由和持久化字段；继续叠加功能会扩大重命名成本。

## 建议修法

- `AgentMate Hub` 全面更名为 `AgentMate Server`，中心服务目录、Python 模块、环境变量和代理路由同步使用 `server`。
- `AgentMate Manager` 全面更名为 `AgentMate Console`，明确它是 Server 托管的 Web 管理控制台。
- 三端统一表述为 `AgentMate App / AgentMate Server / AgentMate Console`。
- 不保留 `HUB_URL`、hub 模块或旧 API 路由别名；对现有本地持久化值做一次性前向迁移。

## 验证

- 全仓运行代码与当前文档中不再存在旧 Hub/Manager 技术命名，历史 issue 的问题背景除外。
- App 使用 `AGENTMATE_SERVER_URL` 接入中心服务，Server API 与 Console 均可真实启动访问。
- App 登录、项目同步、目录代理、评论/通知等原有链路通过回归测试。
- `npx tsc --noEmit`、生产构建及相关 Python 编译检查通过。

## 处理记录

### 2026-07-20 · Codex

- 产品职责统一为 **AgentMate App / AgentMate Server / AgentMate Console**：Server 是中心 API 与权威数据服务，Console 是 Server 同源托管的 Web 管理控制台。
- 全面完成技术重命名：`hub/` → `server/`，本地客户端、同步模块、路由、前端 store/组件、环境变量、启动脚本及当前设计文档全部改用 `server`；未保留旧环境变量、旧 API 路由或模块别名。
- 增加一次性 SQLite 前向迁移，将旧表、列、`origin`、`scope` 与目录来源值改为 `server` 命名；迁移后的本地 DB 与 Server DB 均无旧 `hub_*` 表或索引。
- 运行验收：`AgentMate Server API` 在 `:8100` 正常响应，`AgentMate Console · Web 管理控制台` 正常加载；本地 backend 的 `/api/server/status` 可用且 `/api/hub/status` 不存在。
- 质量验证：回归测试 10/10、TypeScript 类型检查、Vite 生产构建、backend/Server Python 编译均通过；技能页在 1440px 与 900px、明暗主题下均无横向溢出，主题色正确切换。
- 提交：未提交（等待用户明确要求）。
