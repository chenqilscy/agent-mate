---
id: WB-436
title: Server 对象存储与 Local Agent working copy
severity: P1
area: backend
status: open
origin: 🆕 近期改动
files:
  - server:1
  - backend/agent/sandbox.py:1
  - backend/routers/files.py:1
  - backend/routers/runs.py:1
created: 2026-08-08
---

## 问题

父项：[WB-431](archive/2026/WB-400-499.md#wb-431)，依赖 WB-432、WB-433。项目资产和 Run 产物当前以本机 workspace 为权威，无法在 Server-first 模型中跨设备恢复和统一授权。

## 触发场景

用户换设备、Console 查看产物或本机 workspace 丢失时，正式文件没有 Server 对象版本；直接同步整个目录又会重新引入文件冲突系统。

## 影响

P1：资产是会话与 Run 迁移的关键依赖；处理不清会造成数据丢失或隐私越界。

## 建议修法

- Server 建立 asset/artifact metadata、object version、hash、权限和保留策略。
- 对接可配置 object storage，支持短期授权、分片、断点续传、hash/size 校验和孤立上传清理。
- Local Agent 下载为 working copy，明确区分“仅本机”“上传中”“已提交”。
- 外部本机文件只有用户显式上传后才进入项目资产；事件只引用 asset id。

## 验证

- 大文件、断网续传、重复上传、hash 不匹配、权限撤销和孤立 multipart 清理通过。
- 两台设备下载同一对象 hash 一致；未上传本机文件不会出现在 Server/Console。
- Server 删除资产不会误删用户原始外部文件，working copy 清理可审计。
