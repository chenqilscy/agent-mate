# AgentMate Server（中心控制平面服务）

AgentMate 从纯 local-first 走向「本地执行 + 云端控制平面」重构的**中心服务**（见
[`docs/agentmate-server-架构设计.md`](../docs/agentmate-server-架构设计.md)、epic
[`WB-058`](../docs/issues/WB-058-hub-control-plane-epic.md)）。本目录（WB-061）是它的**骨架**：
账号 / 组织 / 项目 / 成员·角色 / 邀请的**权威源**，以及鉴权签发。

> monorepo：与本地 `backend/` 代码解耦、可单独部署与启动，但同仓共享一份 git 历史。
> **绝不承载** LLM 凭据 / 沙箱工作区文件——那些永远只在本地。

## 运行

```bash
cd server
python main.py            # 默认 127.0.0.1:8100
# 可覆盖：AGENTMATE_SERVER_PORT=8100  AGENTMATE_SERVER_DB=/path/to/server.db  AGENTMATE_SERVER_HOST=0.0.0.0
```

依赖 `fastapi` + `uvicorn`（见 `requirements.txt`）。与 backend 同族，本地可复用同一 venv。

## Console 前端

Server 同源托管 AgentMate Console。WB-234 起逐页迁移到 React 19 + Ant Design 6：

```bash
pnpm build:console       # 仓库根执行，输出 server/web/console-dist/
pnpm dev:console         # 可选：:8103 开发服务，/api 代理到 Server :8100
```

全部 Console 页面均由 `server/web/console-dist/` 提供，所有非 `/api/*` 稳定路由都支持直达与刷新；
页面共用同源 Bearer token，并直接调用真实 `/api/*`。

## API（`/api` 前缀）

- **鉴权**：`POST /auth/register`、`POST /auth/login`（→ `{token, account}`）、`POST /auth/logout`、
  `GET /me`、`GET /auth/verify`（token→account，供本地 backend 客户端解析）。
- **组织**：`POST /orgs`、`GET /orgs`、`GET /orgs/{id}/members`、`POST /orgs/{id}/members`。
- **项目**：`POST /projects`、`GET /projects`、`GET/PATCH /projects/{id}`、
  成员 `GET/POST /projects/{id}/members`、`PATCH/DELETE /projects/{id}/members/{account_id}`。
- **邀请**：`POST /projects/{id}/invites`、`GET /invites/{code}`、`POST /invites/{code}/accept`。
- **目录**（预埋，供 P3 下发）：`GET /catalog/{category}`。

鉴权强制：受保护端点无/错 Bearer token 一律 401（不同于本地 backend「无 token 退本地 owner」）。
角色语义与 backend 一致：Owner > Admin > Member > Viewer（Viewer 只读、Member+ 可写、Admin+ 管成员）。

## 边界（WB-061 不做）

同步逻辑（[WB-062](../docs/issues/WB-062-local-hub-sync-protocol.md)）、实时通道、计费/SaaS 多区域、
完整目录下发（[WB-063](../docs/issues/WB-063-hub-migration-and-local-fallback.md)）。
