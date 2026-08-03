---
id: WB-379
title: Server 账号撤销与 App 长期离线令牌缓存语义冲突
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/auth/middleware.py:47
  - server/config.py:50
created: 2026-08-03
---

## 问题
本地命中 Server token 后不再在线校验，默认缓存生命周期 30 天，账号停用不能及时传播到 App。

## 触发场景
管理员停用/删除账号 → 已登录桌面仍使用缓存 token 访问本地团队镜像和执行能力。

## 影响
P1。中央撤销语义与文档承诺不一致；被撤销主体保留长期本机访问窗口。

## 建议修法
为在线 Server 身份增加短校验 TTL、revocation epoch 与周期 introspection；离线超窗时仅允许明确的本地降级作用域并暴露状态。

## 验证
在线缓存过期后重新校验；Server 返回 401 时原子撤销本地身份；短时离线行为有界且有测试。
