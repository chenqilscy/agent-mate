---
id: WB-061
title: Hub 服务骨架 —— 独立中心服务：账号/组织/项目/成员/邀请权威源 + 鉴权签发
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - docs/workbuddy-hub-架构设计.md
  - backend/auth/deps.py:30
  - backend/storage/db.py:68
created: 2026-07-07
---

## 问题

没有中心权威源。账号/组织/项目/成员现都散在各台本机的 SQLite 里
（[db.py](../../backend/storage/db.py) 的 `users`/`projects`/`project_members`），
本地 auth 无 token 就退 `LOCAL_USER_ID`（[auth/deps.py:30](../../backend/auth/deps.py#L30)）。
真正的多人协作需要一个独立服务，作为身份/组织/项目/成员/邀请的 source of truth。

## 触发场景

队友要跨机、跨设备协作同一项目、管理成员与角色——当前没有承载它的中心服务。

## 影响

P1：这是 [WB-058](WB-058-hub-control-plane-epic.md) #2 的核心地基。骨架先立起来（可自托管的单体服务 + 鉴权 + 核心表 + 一组管理 API），后续同步（WB-062）与迁移（WB-063）才有对端。

## 建议修法

按 [架构设计 §3/§7/§9](../workbuddy-hub-架构设计.md)：

- **独立服务、同仓（monorepo）**：放本仓库新目录 **`hub/`**（技术栈沿用 FastAPI；库先 SQLite 亦可，规模上来换 Postgres）。与本地 `backend/` 代码解耦、可单独部署与启动，但共享一份 git 历史。不另起仓库。
- **权威表**：`accounts`、`orgs`/`teams`、`projects`、`project_members`（角色沿用 `Role` 枚举 Owner/Admin/Member/Viewer）、`invites`。多租户由 `org_id` 贯穿。
- **鉴权**：注册/登录 → 签发 token（演进现有 `auth_tokens` 机制）；提供 token 校验端点供本地 backend 作为客户端调用。
- **管理 API**：账号、组织/团队、项目 CRUD、成员增删改角色、邀请生成/接受。
- **目录承载预埋**：`catalog_*`（WB-059/060 的表）在 Hub 侧建同构表 + `scope='builtin'/'org'` 维护端点（供 P3 下发）。
- **不做**：本轮不做同步逻辑（WB-062）、不做实时通道、不做计费/SaaS 多区域。

## 验证

- Hub 服务可独立启动；`py_compile`/最小自测通过。
- 端到端（脚本或 curl）：注册账号 → 登录拿 token → 建组织 → 建项目 → 邀请并加入一名成员并设角色 → 用 token 调受保护端点成功、无/错 token 被拒。
- 角色语义正确：Viewer 只读、Member 可写、Owner/Admin 可管成员（与本地既有 Role 语义一致）。
- 数据落 Hub 库、跨「客户端」可见（模拟两个客户端读到同一项目成员）。
