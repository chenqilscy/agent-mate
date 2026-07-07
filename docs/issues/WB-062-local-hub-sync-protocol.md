---
id: WB-062
title: 本地 ⇄ Hub 同步协议 —— 下行拉取(身份/项目/成员/目录) + 上行 outbox 回传(执行产出)
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - docs/workbuddy-hub-架构设计.md
  - backend/storage/db.py:85
  - backend/auth/middleware.py
created: 2026-07-07
---

## 问题

Hub（[WB-061](WB-061-hub-service-skeleton.md)）立起来后，本地客户端还没有与它同步的机制：
控制平面数据（身份/项目/成员/目录）要能**下行**到本地缓存；执行产出（会话/消息/待办/运行记录）要能**上行**回传 Hub 供团队时间线。且必须**离线可用**——连不上 Hub 时纯本地照跑。

## 触发场景

- 队友 A 在 Hub 建了项目并邀请 B；B 的本地客户端应能拉到该项目与成员并参与。
- A 在本地执行了一段 agent 任务；其会话/待办应回传 Hub，B 能在团队时间线看到（只读镜像 + 动态署名，延续 M7）。
- 断网期间 A 仍能本地执行，联网后自动补传。

## 影响

P1：#2 协作真正跑通的关键一环。依赖 WB-061（对端就绪）。

## 建议修法

按 [架构设计 §6](../workbuddy-hub-架构设计.md)：

- **下行 pull**：本地 backend 作为 Hub 客户端，启动 + 定时 + 按需拉取 identity/projects/membership/catalog 的**增量**（每类带 `version`/`updated_at` 游标，只回变更集）。写本地**镜像表**（`origin='hub'`, read-only）；本机 override（本地技能/自造专家）叠加其上。
- **上行 push（outbox 模式）**：本地执行先落本地库 + 写一条 `outbox` 记录（待同步）；后台 worker 批量推 Hub，确认后标记已同步；断线/离线自动重连补推。会话/消息/运行记录 **append-only**；待办双向用 `updated_at` LWW。
- **访问控制**：本地按缓存的成员表做项目访问判定（延续 WB-050 的项目访问校验，改读镜像成员表）。
- **凭据边界**：同步 payload **绝不含** `LLM_API_KEY`/连接器 secret / 沙箱工作区文件（铁律 4/11）；团队时间线上报**可配置**、默认最小上报（隐私）。
- **回退**：Hub 不可达时所有路径降级为本地 owner，绝不阻断本机使用。

## 验证

- `py_compile` 全过；离线/在线两态各跑一遍。
- 两客户端 E2E：A 建项目/改成员（Hub）→ B 客户端 pull 到；A 本地执行 → 会话/待办 outbox 回传 → Hub 可见 → B pull 到只读镜像（署名正确）。
- 断网执行 → 恢复网络 → outbox 自动补传、无重复、无丢失。
- 抓包/日志确认同步 payload **不含**任何凭据/密钥/工作区文件内容。
- 关闭团队时间线上报开关后，执行产出不再上行。
