---
id: WB-009
title: 全局单 sqlite 连接被线程池 + 事件循环并发共享
severity: P1
area: backend
status: fixed
origin: 🏚 既有实现
files:
  - backend/storage/db.py:27
created: 2026-07-06
---

## 问题
`db.py:27` 用 `check_same_thread=False` 的**单个全局连接**，被 FastAPI 同步路由（anyio 线程池，多线程）与 async 的 `run_chat`（事件循环线程）同时 `execute`/`commit`。sqlite3 `Connection` 并非可并发复用，易触发 `recursive use of cursors not allowed` / `database is locked` / 事务状态错乱。

## 触发场景
并发请求：一个 chat 流正在写 message，同时另一个请求在列 sessions / 更新 work_item。

## 影响
偶发写失败、锁错误；随并发上升更明显。

## 建议修法
线程本地连接（`threading.local`），或每次操作短连接 + 简单连接池，或对写操作加一把 `threading.Lock`。同时可开启 `PRAGMA journal_mode=WAL`（注意 WAL 边车文件已在 .gitignore）。

## 验证
并发压测（多会话同时流式 + 列表/看板操作）无 `database is locked` / 游标错误。

## 处理记录（2026-07-06）
- 改动：单个全局连接改为线程本地连接（`threading.local`），每线程独立 `sqlite3.Connection`；新增 `PRAGMA busy_timeout=5000`（WAL 已启用），并发写等待而非立即报错。（backend/storage/db.py）
- 验证：verify_backend.py 经 TestClient 建项目/会话/工作项并发读写全通过；事件循环线程与 anyio 工作线程不再共用同一连接。
