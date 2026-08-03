---
id: WB-377
title: Relay 周期清理一次异常后永久停止且健康检查无感知
severity: P1
area: backend
status: open
origin: 🆕 近期改动
files:
  - server/main.py:37
created: 2026-08-03
---

## 问题
周期清理循环没有单轮异常隔离、退避、监督或 last_success 健康状态。

## 触发场景
SQLite 临时锁或磁盘抖动使 cleanup 抛异常 → asyncio task 永久退出 → 后续终态 Relay 不再清理但服务仍返回健康。

## 影响
P1。数据库与敏感 payload 可无界增长，现有 retention 保证失效且不告警。

## 建议修法
捕获单轮异常并继续、记录连续失败与成功时间；健康/就绪输出 stale 状态；启动首轮失败应显式处理。

## 验证
注入一次 cleanup 异常后下一轮仍执行；连续失败使 readiness degraded；成功后自动恢复。
