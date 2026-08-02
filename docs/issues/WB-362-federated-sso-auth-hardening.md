---
id: WB-362
title: Server 缺少微信 Google Telegram 联合登录与公网鉴权加固
severity: P1
area: fullstack
status: open
origin: 🆕 用户需求
files:
  - server/routers/auth.py:25
  - server/db.py:84
  - console/src/pages/LoginPage.tsx:1
created: 2026-08-03
---

## 问题

Server 只有本地用户名密码注册登录；没有外部身份绑定、OAuth/OIDC state/nonce/PKCE、Telegram Login Widget 校验，也缺少注册策略、登录限速、token 哈希和口令升级。

## 触发场景

用户希望通过微信、Google 邮箱或 Telegram 登录同一个 AgentMate 账号，或将 Server 暴露给受控远程用户。

## 影响

P1。用户管理和公网身份边界不完整。

## 建议修法

由 Server 统一承载 SSO broker：Google 走 OIDC Authorization Code+PKCE，微信走开放平台 OAuth，Telegram 按官方 Login Widget 数据签名校验；外部身份唯一绑定本地账号。提供 provider 管理、一次性 state、回调、账号绑定/解绑、邀请制注册、登录限速、强口令散列和哈希会话 token。

## 验证

- 三类 provider 的协议校验、state 重放、错误签名、账号冲突和绑定权限测试通过；
- 未配置 provider 不显示入口且失败关闭；
- 密钥只写不回显；
- Console/App 登录与原本地登录回归通过。
