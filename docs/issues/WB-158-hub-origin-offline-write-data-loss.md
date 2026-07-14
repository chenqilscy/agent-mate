---
id: WB-158
title: hub-origin 项目离线新建 work_item/milestone 被下次镜像删除（数据丢失）
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/routers/work_items.py:208
  - backend/routers/milestones.py
  - backend/storage/db.py:1646
created: 2026-07-14
---

## 问题

`work_items.py` create（182-217）：项目是 hub-origin（`_hub_token` 有 token）但 Hub 暂不可达时，`hub_client.create_work_item` 返回 falsy，**回退到本地** `db.create_work_item`（新 UUID、不入 outbox）。下次 `list_items`（Hub 恢复）调 `db.mirror_hub_work_items` → `DELETE FROM work_items WHERE project_id=?` 再只插 Hub 集（`db.py:1646-1663`），**永久丢掉那条离线新建项**。`milestones.py` create + `db.mirror_hub_milestones` 同样。

## 触发场景

在 Manager/Hub 项目里、Hub 短暂抖动时新建一个任务 → Hub 恢复后一次 list 就把它删了，用户以为建好了。

## 影响

P2：静默数据丢失 + 假成功（违反铁律#1）。仅 Hub 部署下。

## 建议修法

hub-origin 项目写在 Hub 不可达时**不要**静默造一条会被镜像抹掉的本地行。最小诚实修法：`tok` 存在但 `create_work_item`/`create_milestone` 返回 falsy → `raise HTTPException(503, "Hub 暂不可达，未创建，请稍后重试")`，让前端如实提示。（更完整方案是接 work_item outbox 重放，另设计。）

## 验证

- `py_compile`。
- 模拟 Hub 不可达对 hub-origin 项目建任务 → 503（前端提示重试），而非静默入库后被抹。
- 回归：纯本地项目（无 token）建任务仍走本地；Hub 可达时正常经 Hub。

## 处理记录（2026-07-14）

- 改动：`backend/routers/work_items.py` 与 `backend/routers/milestones.py` 六处（work_item/milestone 各 create/update/delete）：hub-origin（`tok` 存在）路径若 Hub 调用返回 falsy，改为 `raise HTTPException(503, "Hub 暂不可达，…请稍后重试")`，不再静默回退本地（那条本地行会被下次 `mirror_hub_*` 的 `DELETE ... WHERE project_id=?` 抹掉 → 数据丢失/假成功）。纯本地项目（`tok=""`）不受影响，仍走本地离线优先。
- 验证：py_compile 过。逻辑：`_hub_token` 仅对 `hub_enabled()` + origin=hub 返 token；本地写前已过 `_require_project_write`。（真实 Hub 抖动 E2E 需可控断网，未做；改动为纯控制流。）
- commit：未提交（待用户确认）。
