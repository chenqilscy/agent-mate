---
id: WB-326
title: Server 登录令牌无过期且本地登出未撤销远端令牌
severity: P1
area: fullstack
status: in-progress
origin: 既有实现
files:
  - server/db.py:85
  - server/db.py:792
  - backend/routers/auth.py:81
  - backend/auth/deps.py:22
  - src/stores/authStore.ts:43
created: 2026-07-26
---

## 问题

Server `server_tokens` 只有 `created_at`，没有 `expires_at`；校验只确认 token 是否存在。与此同时，本地
`POST /api/auth/logout` 仅删除 backend 的 `auth_tokens` 缓存，未调用 AgentMate Server 的
`/api/auth/logout`，因此同一 token 在 Server 侧仍可继续使用。

## 触发场景

1. 用户登录后获得 Server Bearer token，前端将其保存到本机。
2. 用户点击退出，本地 backend 删除缓存，前端删除 localStorage。
3. 被复制、泄露或由其他客户端持有的同一 token 仍存在于 Server `server_tokens`。
4. 该 token 没有绝对过期时间，可持续访问 Server，除非直接操作数据库删除。

## 影响

P1：退出登录不能真正终止凭据，且永久 token 扩大泄露后的有效窗口。local-first 离线缓存还会掩盖
Server 侧撤销状态，需要明确的过期边界和可重试撤销流程。

## 建议修法

1. Server token 增加绝对 `expires_at`，登录/注册返回过期时间；校验拒绝并清理过期 token。
2. 本地 `auth_tokens` 同步保存过期时间；离线只允许使用未过期的已验证 token。
3. 本地登出调用 Server 撤销；不可达时先本地失效并持久化待撤销记录，由现有后台同步循环重试。
4. 登出同时清除与该 token 对应的 Server identity，避免后台继续以已退出身份上报。
5. 不把 token 输出到日志、前端提示或测试快照；迁移存量 token 时设置有界兼容期限。

## 验证

- Server/backend 迁移幂等；新旧 token 都有确定的有效期，过期后返回 401 且不能离线恢复。
- 在线登出后 Server `/auth/verify` 立即拒绝原 token。
- 离线登出立即失去本地身份，待 Server 恢复后自动完成远端撤销。
- 未登录访客、离线未过期会话、登录/注册、SSE Bearer 鉴权不回归。
- `py_compile`、Server/backend 相关测试、前端类型检查与真实 API 验证通过。
