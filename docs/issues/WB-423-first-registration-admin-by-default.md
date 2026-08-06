---
id: WB-423
title: 首个注册用户应自动成为平台管理员
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - server/routers/auth.py:54-63
  - server/db.py:1114-1134
created: 2026-08-07
---

## 问题

当前 Server 创建首个平台管理员需要两步：先配置 `AGENTMATE_BOOTSTRAP_ADMIN_SECRET` 环境变量，再调
`POST /api/auth/bootstrap`。这在开发/小团队自托管场景下很重——用户只想开箱即用。

普通注册路由 `POST /api/auth/register` 始终硬编码 `is_platform_admin=False`
（`server/routers/auth.py:59`），即使在零账号的初始状态下也不例外。

## 触发场景

1. 部署 Server（或 rm `server.db` 重来），**不设** `AGENTMATE_BOOTSTRAP_ADMIN_SECRET`
2. 设 `AGENTMATE_SSO_REGISTRATION_POLICY=open`
3. 打开 Console → 注册第一个账号
4. ❌ 注册成功，但账号无平台管理员权限 → 无法创建 / 管理其他账号（`/admin/*` 403）
5. 管理员功能彻底不可达

## 影响

- 自托管/开发部署的门槛不必要地高
- bootstrap 流程是**额外**的安全措施（白盒共享部署）、不应是**唯一**的提权路径
- 零账号时第一个进来的用户天然就是系统 owner，合情合理

## 建议修法

在 `POST /api/auth/register`（`server/routers/auth.py:55-63`）中，`create_account` 前检查
`db.count_accounts() == 0`：若为 true 则 `is_platform_admin=True`，否则保持现有行为。

```python
# 伪代码
is_admin = db.count_accounts() == 0
acc = db.create_account(
    name=name, password=body.password, email=body.email.strip(),
    is_platform_admin=is_admin,
)
```

注意：
- 认证审计日志（`record_auth_audit`）中应区分是"首个注册自动提权"还是"正常的普通注册"。
- `bootstrap_admin` 仍保留 —— `AGENTMATE_BOOTSTRAP_ADMIN_SECRET` 用于白盒/非开放注册部署的强制管理员初始化。
- 如果 `registration_policy != "open"`（当前是 `invite_only`），`/auth/register` 本就不会被调到——这时仍然只有 bootstrap 路径。

## 验证

1. rm 或清空 `server.db`，不设 `AGENTMATE_BOOTSTRAP_ADMIN_SECRET`
2. 设 `AGENTMATE_SSO_REGISTRATION_POLICY=open`，启动 Server
3. `POST /api/auth/register` 注册第一个账号
4. 确认返回的 `account.is_platform_admin: true`
5. 用该 token 调 `GET /admin/*` → 200（非 403）
6. 再注册第二个账号 → `is_platform_admin: false`

## 处理记录（2026-08-07）

- 改动：`server/routers/auth.py:55-63` — `register()` 中 `create_account` 前检查
  `db.count_accounts() == 0`，首个注册用户 `is_platform_admin=True`；审计日志
  action 区分 `bootstrap_first_admin` / `password_registered`。`bootstrap` 路由与
  `AGENTMATE_BOOTSTRAP_ADMIN_SECRET` 完整保留（invite_only 场景的唯一入口）。
- 验证：
  - 清空 DB、`registration_policy=open`、不设 `BOOTSTRAP_ADMIN_SECRET`
  - `POST /api/auth/register` 第 1 个用户 → `is_platform_admin: true` ✅
  - `POST /api/auth/register` 第 2 个用户 → `is_platform_admin: false` ✅
  - 默认 `invite_only` 下 `/auth/register` 依然 403（bootstrap 仍是封闭模式的唯一入口）
- commit：待提交
