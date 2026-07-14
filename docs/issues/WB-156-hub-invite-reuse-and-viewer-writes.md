---
id: WB-156
title: Hub 访问控制 —— 邀请码可无限重用/永不失效 + Viewer 越权（timeline 上报 / org 建项目）
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - hub/routers/invites.py:42
  - hub/config.py:22
  - hub/routers/timeline.py:26
  - hub/routers/projects.py:29
created: 2026-07-14
---

## 问题

Hub（云端控制平面，权威源）三处授权缺口：

1. **邀请码无限重用（P1）**：`invites.py:42-56` `accept_invite` 从不检查 `inv.accepted_by`；`db.mark_invite_accepted` 只是覆盖单列；`create_invite` 用 `ttl=settings.INVITE_TTL`，默认 `HUB_INVITE_TTL=0` = **永不过期**，也无吊销端点。单个邀请码泄漏 → 任何人可反复自助入项目。`get_invite` 的 `accepted` 标志与单数 `accepted_by` 列证明本意是单次。
2. **Viewer 可写团队时间线（P3）**：`timeline.py:26` `post_event` 只判 `project_access_role is None`（成员），不判 `can_write`。Viewer 可往「本应镜像真实执行」的权威时间线灌造假事件。`work_items`/`milestones` 写都用了 `_require_write`，唯 timeline 不一致。
3. **org Viewer 可建项目（P3）**：`projects.py:29` `create_project` 只判 `org_role(...) is None`；只读 org 成员非 None → 可挂新项目（自己成 owner）。

## 触发场景

- Admin 建一个 Member/Admin 邀请码发给 Bob → Bob 接受成成员；该码永久有效，任何后来拿到它的人再 `POST /invites/{code}/accept` 也入项目。
- Viewer `POST /projects/{id}/timeline` 灌造假 session 事件。
- org Viewer `POST /projects {org_id}` 建项目。

## 影响

P1（合起来）：无界自助入组是真实越权；Viewer 越权写是只读语义破坏。仅 Hub 部署（协作）下生效。

## 建议修法

1. `accept_invite`：`if inv.accepted_by is not None: raise HTTPException(409, "邀请码已被使用")`（保持单次语义）。`hub/config.py` `INVITE_TTL` 默认给非零（如 7 天 `604800`），保留 0=永久由部署显式选择。
2. `timeline.post_event`：`role = project_access_role(...)`，`role is None` → 404，`not can_write(role)` → 403。
3. `projects.create_project`：`body.org_id` 非空时 `if not can_write(db.org_role(...)): raise 403`。

## 验证

- `py_compile`（hub）。
- 同一邀请码第二次 accept → 409；Viewer post timeline → 403；org Viewer create project → 403。
- 回归：首次 accept 正常入组；Admin/Owner 正常上报 timeline / 建项目。

## 处理记录（2026-07-14）

- 改动：
  - `hub/routers/invites.py` `accept_invite`：`inv.accepted_by is not None` → 409（单次使用）。
  - `hub/config.py` `INVITE_TTL` 默认 `604800`（7 天），保留 0 可显式回到永久。
  - `hub/routers/timeline.py` `post_event`：`import can_write`，`role is None`→404、`not can_write(role)`→403。
  - `hub/routers/projects.py` `create_project`：`body.org_id` 时 `not can_write(org_role)`→403。
- 验证：py_compile 过；隔离 Hub（scratchpad DB）TestClient 冒烟——邀请码首次 accept 200、重用 409；Viewer post timeline 403、owner 200。
- commit：未提交（待用户确认）。
