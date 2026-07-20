---
id: WB-061
title: Hub 服务骨架 —— 独立中心服务：账号/组织/项目/成员/邀请权威源 + 鉴权签发
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - docs/agentmate-hub-架构设计.md
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

按 [架构设计](../agentmate-server-架构设计.md)：

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

## 处理记录（2026-07-07）

### 改动 —— 新增独立同仓服务 `hub/`（FastAPI + SQLite，与 backend 解耦、可单独启动，默认 :8100）
- `hub/config.py`：`HUB_DB`/`HUB_PORT`/`HUB_HOST`/pbkdf2 迭代/邀请 TTL。
- `hub/models.py`：`Role` 枚举与 backend **逐字一致**（Owner>Admin>Member>Viewer）+ `ROLE_RANK`/`can_write`/`can_manage`；`Account`/`Org`/`Project`/`Invite` dataclass。
- `hub/db.py`：thread-local 连接 + WAL + busy_timeout（沿用 backend WB-009 做法）；表 `accounts`/`hub_tokens`/`orgs`/`org_members`/`projects`/`project_members`/`invites`/`catalog_items`(目录预埋)；DAO 全套；pbkdf2 口令散列。
- `hub/auth.py`：`current_account` **强制鉴权**（无/错 token → 401，不同于本地 backend 的退本地 owner）；`parse_member_role`（Owner 不可经成员接口赋予）。
- `hub/routers/`：`auth`(register/login/logout/me/**verify** token→account 供本地 backend)、`orgs`(建/列/成员)、`projects`(CRUD+成员/角色，`project_access_role` 单闸)、`invites`(建/查/接受)、`catalog`(预埋 GET)。
- `hub/main.py`（FastAPI + CORS + /api/health + 挂载 + uvicorn 入口）、`requirements.txt`、`README.md`、`.gitignore`（hub.db 不入库）。

### 语义
- access = owner OR 成员；**Viewer 只读、Member+ 可写、Admin+ 管成员**（与 backend 一致）；owner 隐式、不作成员；邀请码 accept → 加为项目成员（角色由邀请定）。多租户由 `org_id` 贯穿。
- 边界（不做）：同步逻辑（WB-062）、实时通道、计费/SaaS；**LLM 凭据 / 沙箱文件绝不上云**。目录仅预埋表 + 最小读端点，完整下发是 WB-063。

### 验证
- `py_compile` 全部 hub .py 通过。
- **TestClient E2E 31 项全过**（隔离 HUB_DB）：register/login/logout/me/verify；dup-name 409、wrong-pw 401、no-token/bad-token 401；建组织(owner)；建项目(owner)、非成员 404；邀请→B 看到项目名→B 接受成为 Member→成员列表(owner+member)正确→B 列出共享项目为 Member；角色门控：Member 可写·不可管(403)、降级 Viewer 后只读(403)·仍可读、Admin 可管；owner-as-member 400、unknown 404、invalid-role(Owner) 400；自退；跨账号读到同一项目（跨客户端可见）；catalog 预埋端点。
- **独立启动**：`python main.py` 于 :8123 起 uvicorn，`/api/health` → `{"ok":true,"service":"hub"}`，live `POST /api/auth/register` → 200。

### 后续
- 与 backend 的 `Role`/成员·目录数据契约将来按需抽到共享模块（架构设计 §9）；本轮先在 hub 内自带，避免跨目录耦合。
- 下一步 WB-062（本地 ⇄ Hub 同步）：本地 backend 作为客户端调 `GET /api/auth/verify` 解析 token、拉取项目/成员、回传执行产出。

commit：（见下）。
