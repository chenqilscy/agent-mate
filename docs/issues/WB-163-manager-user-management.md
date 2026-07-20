---
id: WB-163
title: Manager 用户管理功能 —— 平台账号 admin CRUD（列表/建/改/重置密码/删）
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - hub/db.py
  - hub/routers/accounts.py
  - hub/main.py:76
  - hub/web/console.html:347
created: 2026-07-14
---

## 问题

AgentMate Manager（Hub，`hub/`）是账号权威源（`accounts` 表 + `/api/auth/*`），
`is_platform_admin` 概念已存在（首个注册账号自举为平台管理员，`hub/db.py:314`），
但**没有任何用户/账号管理端**：`console.html` 只有登录/注册表单（`au-name`），
没有「查看全部平台用户、创建账号、改人格/套餐/管理员、重置密码、删账号」的管理页。
平台管理员无法运营用户，且 App 端要「在 Manager 验证并两端打通」（见 [WB-164](WB-164-app-login-via-manager.md)）
时，Manager 缺一个可见的用户台账去核对/管理。

## 触发场景

以平台管理员登录 Manager（`http://127.0.0.1:8100`）→ 侧栏「系统」分区没有「用户」入口 →
无法看到系统里有哪些账号、谁在线、各自项目数，也无法新建/停用/重置账号。

## 影响

P1：用户管理是「在 Manager 验证 + 两端打通」诉求的一半。无管理端则账号只能靠注册表单自助创建，
管理员既看不到也管不了；WB-164 打通后 App 用户全部落 Manager，更需要一个权威台账。

## 建议修法

1. `hub/db.py` 增账号管理助手：`list_accounts()`（含 last_seen/online、拥有+参与项目数）、
   `update_account(id, name/email/plan/is_platform_admin)`、`set_account_password(id, pw)`、
   `delete_account(id)`（级联清 tokens/成员行）、`owned_projects_count(id)`、`count_platform_admins()`。
2. 新增 `hub/routers/accounts.py`，全部 `is_platform_admin` 门禁（复用 settings.py 的 `_require_admin` 模式）：
   `GET /api/accounts` 列表、`POST /api/accounts` 建、`PATCH /api/accounts/{id}` 改、
   `POST /api/accounts/{id}/password` 重置、`DELETE /api/accounts/{id}` 删。
   守卫：不能删自己、不能删最后一个平台管理员、拥有项目的账号需先移交/删项目才能删。
   在 `hub/main.py` include。
3. `console.html`：「系统」分区加 `${nvItem("users","用户")}`（admin only），新增 `usersView(m)`——
   富列表（名/套餐/管理员徽章/在线/项目数/创建时间）+ 新建表单 + 逐行编辑/重置密码/切管理员/删。
   **所有 id/class 用 `um-` 前缀**（并发共享树防撞，见既往 WB-100/101/102 经验）。视觉沿用既有
   `.card/.list-item/.field/.pill/.badge` 与 `.np-*` 弹窗骨架，零重设计（铁律 2）。

## 验证

- `cd hub && python -m py_compile db.py routers/accounts.py main.py`。
- 启 Hub :8100，以平台管理员登录 console → 「用户」页能列出全部账号；建一个账号 → 出现在列表；
  改其套餐/切管理员 → 刷新仍在；重置密码 → 用新密码能登录；删一个非 owner 账号 → 消失；
  删自己/最后管理员/有项目的账号 → 被明确拦截报错。
- 非管理员账号看不到「用户」入口，直接打 `/api/accounts` 返回 403。

## 处理记录（2026-07-14）

- 改动：
  - `hub/db.py` 增账号管理助手：`owned_projects_count`/`member_projects_count`/`count_platform_admins`/
    `_account_admin_view`（含 last_seen/online/项目数，绝不含 password_hash）/`list_accounts`/
    `get_account_admin_view`/`update_account`/`set_account_password`/`delete_account`（级联清 hub_tokens + project_members）。
  - 新增 `hub/routers/accounts.py`：`GET/POST /api/accounts`、`PATCH /api/accounts/{id}`、
    `POST /api/accounts/{id}/password`、`DELETE /api/accounts/{id}`，全部 `_require_admin` 门禁。
    守卫：删自己 400 / 删最后管理员 400 / 撤销最后管理员 400 / 有项目账号删 400 / 重名 409。在 `hub/main.py` include。
  - `hub/web/console.html`：「系统」分区加 `nvItem("users","用户")`（admin only）+ `render` 分发 +
    `usersView`/`umRenderList`/`umEditModal`/`umPasswordModal`/`umDeleteModal`（全 `um-` 前缀，复用
    `.card/.list-item/.field/.pill/.badge` 与 `expModal/expClose` 的 `.np-*` 弹窗骨架）。
- 验证：
  - `python -m py_compile db.py routers/accounts.py main.py` 通过；console 内联脚本 `node --check` 无语法错。
  - 隔离 Hub :8199（scratchpad DB）跑 20/20 API 断言：列表富字段、不泄 password_hash、建/重名 409、
    改套餐邮箱、重置密码后新旧密码分别 200/401、非管理员 403、删自己/最后管理员/有项目账号均 400、删普通账号 200、
    双管理员后可降级。
  - 独立 headless chromium 走 CDP 以平台管理员登录 console → 「用户」页真渲染 4 账号（徽章 平台管理员/🟢 在线/
    套餐/项目数/你 全对，12 个操作按钮），编辑弹窗正常打开（截图存证）。
- commit：待提交（与 WB-164 同源一并提交）。
