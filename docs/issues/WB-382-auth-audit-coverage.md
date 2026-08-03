---
id: WB-382
title: 平台管理员变更及 SSO 身份操作缺少认证审计
severity: P2
area: backend
status: open
origin: 🆕 近期改动
files:
  - server/routers/accounts.py:65
  - server/sso_store.py:320
created: 2026-08-03
---

## 问题
账号资料更新包含 is_platform_admin 升降级但未记录 auth audit；SSO 登录、绑定、解绑同样没有完整身份审计。

## 触发场景
管理员授予平台权限，或用户通过外部身份登录/绑定/解绑 → 事后无法从认证审计还原 actor、target、provider 与前后状态。

## 影响
P2。高风险身份变更不可审计，影响安全调查与合规。

## 建议修法
与状态变更同一事务写 append-only auth audit；只记录必要元数据，不记录 token、secret、authorization code。

## 验证
管理员升降级和 SSO login/link/unlink 均产生脱敏审计；失败事务不留下成功审计。
