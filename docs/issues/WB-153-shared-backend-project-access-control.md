---
id: WB-153
title: 共享后端多用户隔离漏洞 —— 会话可绑他人项目、Viewer 可执行/写、/stop·/answer 无 owner 校验
severity: P0
area: backend
status: fixed
origin: 既有实现
files:
  - backend/routers/sessions.py:52
  - backend/routers/chat.py:64
  - backend/routers/chat.py:99
  - backend/routers/files.py:59
created: 2026-07-14
---

## 问题

延续 WB-013/WB-050 的 owner/成员隔离，在共享后端（`HUB_URL` 已设、多 Hub 账户）下仍有三处缺口：

1. **`sessions.py:52` `create_session` 不校验 `body.project_id` 的访问权**。对比 `chat.py:64`（新建项目会话时会 `project_access_role(...) is None` → 404），`sessions.py` 直接把调用方给的任意 `project_id` 挂到自己的会话上，毫无校验。
2. **`chat.py:64` 只判 `is None`，Viewer（只读成员）可发起项目执行**。Viewer 角色非 None → 通过校验 → 驱动 agent 在该项目沙箱内跑 `write_file`/`run_command`，写他本该只读的项目。`files.py:55` 的 `?project=` 分支已有 Viewer 写守卫，执行链路却没有。
3. **`chat.py:99/109` `/stop`、`/answer` 完全无 owner 校验**。仅凭路径 `session_id` 调 `runtime.request_stop`/`submit_answers`。队友（M7 C3 可只读拿到他人 session id）可 `POST /answer` 向别人挂起的 `ask_user` 注入任意文本，或 `POST /stop` 中止其运行。
4. **`files.py:59` `_select_root` 的 session 分支**只校验 session owner，再用 `project_root(s.project_id)`，不复核 project 访问权/Viewer 写——是 #1 的下游放大点。

## 触发场景

- 攻击者（同后端另一账户）`POST /api/sessions {"project_id":"<他人项目>"}` → 拿到自己名下的 session → `GET/POST /api/files/*?session=<该session>` 读/写他人项目沙箱；`POST /api/chat {session_id}` 在其中跑工具。
- 项目 Viewer `POST /api/chat {project_id, text}` → agent 写他只读的项目。
- 队友拿到他人 live session id → `POST /api/chat/{id}/answer` 注入文本 / `/stop` 中止。

## 影响

P0：跨账户读写他人项目工作区 + 跨用户注入/中止 agent 运行。仅在共享后端多用户配置下可触发（纯单机 LOCAL_USER 无害），但那正是 M7 多用户要保护的形态。

## 建议修法

1. `sessions.create_session`：`body.project_id` 非空时 `if db.project_access_role(project_id, user.id) is None: raise 404`（照抄 chat.py:64）。
2. `chat.py` 新建项目会话分支：`role = project_access_role(...)`，`role is None` → 404，`role == Role.VIEWER` → 403（只读成员不能执行）。
3. `chat.py` `stop`/`answer`：先 `current_user()` + `db.get_session(session_id, owner_id=user.id)`，无则 404 再 dispatch。
4. `files._select_root` session 分支：若 `s.project_id`，复核 `project_access_role` 并对 `write` 施加 Viewer 守卫（防御纵深）。

## 验证

- `py_compile`。
- 另一账户建带他人 project_id 的 session → files 读该 project 应 404；Viewer 发 project chat 应 403；非 owner `/answer`/`/stop` 应 404。
- 回归：owner 自己的 project 会话、成员正常读、合法 answer/stop 仍工作。

## 处理记录（2026-07-14）

- 改动：
  - `backend/routers/sessions.py` `create_session`：`body.project_id` 非空时 `project_access_role(...) is None` → 404（照 chat.py 守卫）。
  - `backend/routers/chat.py`：`import Role`；新建项目会话分支捕获 `role`，`None`→404、`VIEWER`→403（只读不执行）；`stop`/`answer` 先 `db.get_session(session_id, owner_id=current_user().id)`，无则 404。
  - `backend/routers/files.py` `_select_root` session 分支：若 `s.project_id` 复核 `project_access_role` + `write` 的 Viewer 守卫（防御纵深）。
- 验证：py_compile 过；隔离 DB + contextvar 直调路由函数的 TestClient 冒烟全过——攻击者建他人 project 会话/发 project chat/停·答他人会话均 404，Viewer 执行 403，owner happy 路径 200。
- commit：未提交（待用户确认）。
