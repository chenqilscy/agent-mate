---
id: WB-013
title: owner_id 隔离未在路由生效（files 可跨项目读）
severity: P2
area: backend
status: fixed
origin: 🏚 既有实现
files:
  - backend/storage/db.py:173
  - backend/storage/db.py:325
  - backend/routers/files.py:40
  - backend/routers/chat.py:49
created: 2026-07-06
---

## 问题
DAO（`get_session` / `get_project` / `get_work_item` / `list_work_items`）只按主键查、不带 owner；路由层（chat/sessions/projects/work_items/files）均无 owner 校验。`files.py` 的 `_select_root(session/project)` 直接按传入 id 打开对应工作区并允许 `/content`、`/download` —— **当前就可用任意 project_id 越权读别人项目文件**。

数据模型宣称「多用户 M1 预埋、切 auth 只改一处」，但路由从不按 owner 过滤，切上真实 auth 后即为水平越权。

## 触发场景
伪造/枚举 project_id / session_id 调 `/api/files/content?project=<别人的>`。

## 影响
当前单用户影响有限，但隔离承诺为假，files 跨项目读已可复现；上真实 auth（M7）前必须修。

## 建议修法
DAO 查询带 `owner_id` 谓词，或在路由统一校验 `resource.owner_id == current_user().id`。

## 验证
用非本人 owner 的 project_id 请求 files/sessions/projects → 返回 404/403。

## 处理记录（2026-07-06）
- 改动：`get_session/get_project/get_work_item` 加可选 `owner_id` 谓词；chat/sessions/projects/work_items/files 路由统一按 `current_user().id` 校验，越权/伪造 id 返回 404；files `_select_root` 也做归属校验，堵住跨项目读文件。（backend/storage/db.py, backend/routers/*.py）
- 验证：verify_backend.py「foreign project/session/files-tree/files-content 404」全 PASS；本人资源仍 200。
