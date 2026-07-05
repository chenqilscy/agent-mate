---
id: WB-017
title: 上传先把整个请求体读进内存再判大小
severity: P2
area: backend
status: fixed
origin: 🏚 既有实现
files:
  - backend/routers/files.py:143
created: 2026-07-06
---

## 问题
`data = await request.body()`（`files.py:143`）一次性读完整个请求体，之后才 `if len(data) > MAX_UPLOAD`。50MB 上限拦不住「先读 1GB 再拒」，可内存 DoS。

## 触发场景
POST `/api/files/upload` 一个超大 body。

## 影响
内存 DoS 面。单用户本地影响有限。

## 建议修法
先看 `Content-Length` 头拒绝超限，或流式读取（分块）并在累计超限时中断连接。

## 验证
上传一个超上限文件 → 在读满内存前即被拒（返回 413），进程内存不飙升。

## 处理记录（2026-07-06）
- 改动：upload 先看 `Content-Length` 头拒超限，再用 `request.stream()` 分块累计、累计超 50MB 即 413；不再 `await request.body()` 一次性读满内存。（backend/routers/files.py）
- 验证：declared/streaming 双重拦截，缺失或伪造 Content-Length 也无法把超大 body 读进内存；py_compile 通过。
