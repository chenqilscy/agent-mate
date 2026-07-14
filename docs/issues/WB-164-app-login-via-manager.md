---
id: WB-164
title: App 登录经 Manager 验证 + 两端用户数据打通（Manager 权威 + 离线兜底）
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/routers/auth.py
  - backend/hub_client.py:94
  - backend/auth/deps.py:28
created: 2026-07-14
---

## 问题

App 与 Manager 各有一套**互不相通**的账号库：
- App 的 `LoginModal` → `api.login` → backend `POST /api/auth/login`（`backend/routers/auth.py:42`）
  只在**本地 `users` 表**校验（`get_user_by_name` + `verify_password`），**从不问 Manager**。
- Manager（Hub）才是账号权威源（`accounts` 表 + `/api/auth/*`）。
- 已有的桥（WB-062，`backend/auth/middleware.py`）只在「一个 Hub token 已经到达时」把账号镜像进本地；
  `/api/hub/login` 代理（WB-067）虽存在，但 App 主登录表单**没走它**。

结果：在 Manager 建的账号无法登录 App，在 App 注册的账号 Manager 不知道——两端用户没打通。

## 触发场景

配置了 `HUB_URL`（App 已接 Manager）后，用 Manager 里的账号密码在 App 登录 → 失败（本地无此用户）；
在 App 注册一个账号 → 只落本地 `users`，Manager 用户台账里查不到。

## 影响

P1：这是「App 端登录需在 Manager 验证、两端用户数据完全打通」诉求的另一半（配 [WB-163](WB-163-manager-user-management.md)）。
不改则协作身份始终分裂。

## 建议修法（决策：Manager 权威 + 离线兜底；不批量迁移，往后统一）

1. `backend/hub_client.py` 加 `hub_login_ex(name, pw, register) -> (status, payload)`，区分
   `"ok"`（200，带 `{token, account}`）/ `"rejected"`（Manager 明确 4xx：401 密码错、409 重名、400）/
   `"unreachable"`（网络错/5xx/超时）。现有 `hub_login`（吞错返 None）保留不动。
2. `backend/routers/auth.py` 改 `login`/`register`——仅当 `hub_client.hub_enabled()` 时：
   - `login`：`ok` → 用 Hub token，就地镜像账号（`upsert_external_user`+`cache_token`+`set_hub_identity`）
     后返回 `{token, user}`；`rejected` → 401（Manager 权威，不回退让密码错被本地放行）；
     `unreachable` → **回退本地 users**（离线/单机仍可登录）。
   - `register`：`ok` → 同样镜像并返回；`rejected` → 透传 409/400；`unreachable` → 诚实 503
     （不静默建分裂的本地账号，遵循 WB-158 原则）。
   - `HUB_URL` 空（未接 Hub）→ 完全走原本地路径，纯本地零变化（铁律/离线优先）。
3. 不做存量本地用户批量迁移（密码只存哈希无法重建）；历史本地用户经 `unreachable` 兜底继续可用，
   新登录/注册经 Manager 统一。前端 `LoginModal`/`authStore` **无需改**（同一 `/api/auth/*` 契约）。

## 验证

- `cd backend && ./.venv/Scripts/python.exe -m py_compile routers/auth.py hub_client.py`。
- 启 Hub :8100 + backend :8000（设 `HUB_URL=http://127.0.0.1:8100`）：
  - 在 Manager 建账号 alice/alice123 → 在 App 用 alice/alice123 登录**成功**，`/api/me` 返回 alice；
  - App 注册新账号 bob → Manager 「用户」页出现 bob（两端打通）；
  - Manager 里密码错 → App 登录 401（不被本地放行）；
  - 停掉 Hub 后，本地历史用户仍能登录（兜底）；注册返回 503（诚实）。
- `HUB_URL` 清空重启 backend → 本地注册/登录照旧（回归旧路径）。

## 处理记录（2026-07-14）

- 改动：
  - `backend/hub_client.py` 增 `hub_login_ex(name,pw,register) -> (status,payload)`：200→`("ok",{token,account})`、
    4xx→`("rejected",{code,detail})`、网络错/5xx/超时/未接→`("unreachable",None)`，绝不抛。旧 `hub_login` 保留。
  - `backend/routers/auth.py` 重写 `login`/`register`（仅当 `hub_client.hub_enabled()`）：
    `login` ok→就地镜像（`upsert_external_user`+`cache_token`+`set_hub_identity`）返 {token,user}；rejected→401；
    unreachable→回退本地 users。`register` ok→镜像返回；rejected→透传 409/400；unreachable→诚实 503。
    未接 Manager → 完全走原本地路径。加 `_mirror_hub_account` 复用助手。前端零改。
- 验证：
  - `py_compile routers/auth.py hub_client.py` 通过。
  - 隔离 backend :8099（HUB_URL→隔离 Hub :8199）跑 9/9 断言：Manager 账号 dave 在 App 登录成功、
    `/api/me` 解析为 dave、**App token == Hub token**（直接打 Hub /me 也认，统一身份）、密码错 401 不回退、
    App 注册 carol 落到 Manager（Hub 直登 200）、重名 409 透传、短密码 400。
  - 离线兜底：先以 HUB_URL="" 的 backend 本地注册 solo（200）；换 dead HUB_URL 复用同库 → 登录 solo 回退本地 200、
    错密码 401、注册 solo2 诚实 503。HUB_URL="" 时本地注册/登录 200（零变化）。
- commit：待提交（与 WB-163 同源一并提交）。
