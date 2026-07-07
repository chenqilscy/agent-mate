---
id: WB-073
title: /api/hub/status 的 linked 判定忽略当前 Hub token，登录后讨论 UI 不解锁
severity: P1
area: backend
status: fixed
origin: WB-067 Slice 1 缺陷（真机 E2E 发现）
files:
  - backend/routers/hub.py
created: 2026-07-08
---

## 问题

`GET /api/hub/status` 的 `linked` 只查 `db.get_hub_link(LOCAL_USER_ID)`（WB-063 迁移用的
「本地所有者↔Hub 账号」绑定），**完全不看请求携带的 Authorization token**。

但 WB-067 的连接模型是「登录即以 Hub 账号身份操作」（app token = Hub token），登录并**不会**
写 LOCAL_USER 的 hub_link（那是「导入本地项目」才做的迁移动作）。于是：

- 登录成功后 `/hub/status` 始终返回 `linked: null`。
- 前端 `hubStore` 据此认为未连接 → `HubCommentsPanel` 停在「连接引导」、`HubConnectModal`
  的「登录并连接」按钮永久卡在「连接中…」（`connect()` 已 resolve 但 `linked` 不翻转）。
- **结果：登录后讨论功能永远打不开。**

## 触发场景

真机 E2E：起 Hub + backend（HUB_URL 指向 Hub）+ 前端 → 项目「讨论」tab → 连接 Hub → 用真实
Hub 账号登录 → 服务端 login/verify/pull 全 200，但 UI 不切换到讨论视图。

## 影响

P1：WB-067 的核心入口（连接 Hub → 讨论）被阻断。评论/在线/@提及后端代理本身是好的（它们透传
token 给 Hub），仅 `linked` 判定错。tsc/build/Slice1 的 API E2E 未覆盖「登录后 status 语义」，故漏网。

## 建议修法

`hub_status` 读 Authorization、用 `hub_client.verify_token(bearer)` 判定当前是否已以某 Hub 账号连接；
verify 命中即 `linked = {account_id,name}`。保留 LOCAL_USER hub_link 作兜底（迁移场景）。

## 验证

- `py_compile`；硬重启 :8000。
- 真机：登录后 `/hub/status` 返回 `linked:{name:"alice"}` → 模态切到已连接态、讨论面板解锁。
