---
id: WB-388
title: 登录方式与最后管理员不变量在事务外校验存在并发竞态
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - server/sso_store.py:530
  - server/db.py:1193
  - server/db.py:1312
  - server/routers/accounts.py:65
created: 2026-08-04
---

## 问题
最后登录方式、最后平台管理员等关键不变量在 `BEGIN IMMEDIATE` 之前读取，校验和状态写入不属于同一个串行化事务。

## 触发场景
两个并发身份解绑、密码登录禁用与身份解绑交错，或两个管理员并发降权/暂停/删除 → 两个请求都基于旧计数通过 → 最终账号失去全部登录方式或平台失去全部管理员。

## 影响
P1。可造成账号或整个控制平面不可恢复锁死，单请求回归测试无法发现。

## 建议修法
把 guard 下沉到 Server DB/SSO store，在 `BEGIN IMMEDIATE` 后重读目标行和计数并执行更新；路由只映射领域错误。为并发解绑、降权、暂停、删除和禁用密码增加真实双连接回归。

## 验证
并发请求最多一个成功，另一个稳定返回领域冲突；事务回滚不留下成功审计；正常单请求路径和 Console 行为不回归。
