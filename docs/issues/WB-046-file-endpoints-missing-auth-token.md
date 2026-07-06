---
id: WB-046
title: 登录用户上传/下载文件不带 Bearer token —— uploadFile 原生 fetch 与 downloadUrl 明文 URL 绕过鉴权
severity: P1
area: frontend
status: fixed
origin: M7 C1 回归
files:
  - src/lib/api.ts:144
  - src/lib/api.ts:153
  - backend/routers/files.py
created: 2026-07-06
---

## 问题

M7 C1 给 REST 加了 Bearer 鉴权：`get()` / `send()` 两个 helper 统一带上
`authHeaders()`（localStorage 里的 token）。但 `api.ts` 里有两个文件相关接口**没走这两个
helper**，因此登录用户的请求不带 token，被后端当成「本地所有者」处理：

1. **`uploadFile`（`api.ts:144`）** 用的是**原生 `fetch`**，没有 `...authHeaders()`：
   ```ts
   const r = await fetch(`${API_BASE}/files/upload${q}`, { method: 'POST', body: file })
   ```
   → 登录用户上传时无 token → 后端 `current_user()` 回退到本地所有者 → 对方并非该项目
   的 owner/member → `_select_root` 返回 **404/403**，上传失败。哪怕是上传到**自己登录账号
   名下**的项目也失败（本地所有者 ≠ 登录账号）。

2. **`downloadUrl`（`api.ts:153`）** 返回一个**明文 URL 字符串**，被当作 `<a href>` / `<img src>`
   直接用，浏览器原生请求**无法携带 Authorization 头** → 同样被当本地所有者 → 跨账号/共享项目
   文件下载 404。

其余文件接口没问题：`filesTree`/`fileContent`/`fileUsage` 走 `get()`、`mkdir`/`renameFile`/
`deleteFile` 走 `send()`，都已带 token。

## 影响

- 只影响**已登录**（M7 真账户）用户；单机免登录模式全程本地所有者，不受影响。
- 症状：登录后在项目云盘/资产里上传文件失败；下载/预览二进制文件（图片等）404。
- 属 C1 鉴权覆盖不全的回归，C2 让「共享项目文件」可用后此坑会被真实触发。

## 建议修法

- **上传（清晰、直接）**：给 `uploadFile` 的 `fetch` 加 `headers: { ...authHeaders() }`。
  一行修复。
- **下载（需设计）**：明文 URL 带不了头，两种方案择一：
  1. 前端把 `downloadUrl` 改成 **fetch(带 authHeaders) → blob → objectURL** 再喂给
     `href`/`src`（改动在消费方）；
  2. 后端 `download`（及必要的 content 二进制）接受 `?token=` 查询参数作为鉴权回退，
     `downloadUrl` 拼上 token。方案 2 简单但把 token 放进 URL（日志/历史可见），需权衡。
  推荐方案 1（token 不进 URL）。

## 验证

- 登录一个真账户 → 建项目 → 项目云盘上传一个文件应 200 且落到该账户项目工作区。
- 共享项目：成员登录后上传应成功（Viewer 应被后端 403，非 404）。
- 下载/预览该文件应成功（不再 404）。
- 单机免登录模式回归：上传/下载照常。

## 处理记录

2026-07-06 fixed（commit 待）：
- **上传**：`uploadFile` 的原生 `fetch` 加 `headers: authHeaders()`，与 `get()`/`send()` 一致带 token。
- **下载**：采用推荐的方案 1——`downloadUrl`（返回明文 URL）替换为 **`downloadFile(path, name, opts)`**：
  用 `fetch(带 authHeaders)` 取字节 → `blob` → `URL.createObjectURL` → 触发 `<a download>` → 延时
  `revokeObjectURL`。token 只在请求头、不进 URL。三个调用点（AssetsManager / ProjectWork /
  FileViewer）改为 `void api.downloadFile(...)`。
- 验证：`tsc` + 生产构建通过；无残留 `downloadUrl` 引用。后端契约此前已在 M7 C2 证明（带 token 的成员
  上传 200、Viewer 403、非成员 404），本修复即让前端把 token 带上以满足该契约。
