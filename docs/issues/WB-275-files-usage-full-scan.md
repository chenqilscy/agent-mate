---
id: WB-275
title: files usage 连续请求每次全量遍历工作区
severity: P3
area: backend
status: fixed
origin: 🏚 迁移遗留
files:
  - backend/routers/files.py:156
created: 2026-07-22
---

## 问题
`GET /files/usage` 每次都执行 `base.rglob('*')` 并 stat 所有文件。大工作区中打开或刷新资产面板会重复支付完整扫描成本。

## 触发场景
项目工作区包含大量依赖或生成文件，短时间内连续刷新资产面板，每次 usage 请求都重新遍历。

## 影响
P3。FastAPI 会在线程池执行同步路由，不阻塞事件循环，但请求本身慢且重复消耗磁盘 IO。

## 建议修法
增加按工作区隔离的短 TTL 缓存；本路由的上传/删除操作立即失效。Agent/外部写入无法统一拦截，依靠短 TTL 自动收敛，避免长期陈旧。

## 验证
- 同一工作区 TTL 内连续请求只扫描一次。
- 不同工作区不串值。
- 上传/删除失效后重新扫描并反映新大小。
- 后端编译和回归测试通过。

## 处理记录（2026-07-22）
- 改动：`/files/usage` 增加按解析后工作区路径隔离的 2 秒线程安全缓存；并发 miss 只扫描一次；上传/删除后立即失效，无法统一拦截的 agent/外部写入由短 TTL 自动收敛。
- 验证：`files.py` 与测试文件编译通过；`test_files_usage_cache` 2 项通过（复用/失效、跨工作区隔离）；隔离临时 DB/工作区的 FastAPI TestClient 对 `/api/files/usage` 连续请求两次均返回 `200`、`used=5`、`quota=5368709120`。
- commit：本提交。
