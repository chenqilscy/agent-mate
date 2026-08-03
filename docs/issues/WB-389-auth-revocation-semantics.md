---
id: WB-389
title: 暂停与身份解绑后的 App 会话撤销语义不一致
severity: P2
area: backend
status: open
origin: 🆕 近期改动
files:
  - backend/auth/deps.py:23
  - backend/config.py:202
  - server/routers/sso.py:180
  - docs/sso-deployment.md:81
created: 2026-08-04
---

## 问题
Server 暂停账号会立即删除中心 token，但 App 默认接受五分钟在线缓存、Server 不可达时接受一小时离线宽限；部署文档却要求 App/Console 立即 401。用户自助解绑身份也不撤销会话，而管理员解绑会撤销。

## 触发场景
管理员暂停疑似泄漏账号，或用户解绑受损 Provider → 已登录 App 继续使用本地执行能力直到缓存窗口结束；不同解绑入口产生不同 token 结果。

## 影响
P2。local-first 可用性与中心止损语义没有明确契约，安全验收会得到不一致结果。

## 建议修法
明确并实现一种一致策略：在线时对安全敏感状态采用短 TTL/服务端 session epoch，离线宽限在 UI 和文档明确；所有身份解绑在同一事务中撤销该账号会话。Console 直连 Server 继续立即失效。

## 验证
自助和管理员解绑具有一致撤销结果；暂停后的在线 App 在声明窗口内拒绝，离线宽限可配置且有明确状态；文档、API 与回归测试一致。
