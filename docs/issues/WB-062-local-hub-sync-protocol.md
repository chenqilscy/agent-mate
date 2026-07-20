---
id: WB-062
title: 本地 ⇄ Hub 同步协议 —— 下行拉取(身份/项目/成员/目录) + 上行 outbox 回传(执行产出)
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - docs/agentmate-hub-架构设计.md
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

按 [架构设计 §6](../agentmate-hub-架构设计.md)：

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

## 实现分期与进度

分三期，每期可独立交付、离线优先：

### Phase 1 —— 鉴权桥 + Hub 客户端（✅ 完成并验证，2026-07-07）
本地 backend 能识别 Hub 签发的 token，安全非破坏、离线全保。
- `backend/config.py`：`HUB_URL`（空 = 未接 Hub = 纯本地）+ `HUB_TIMELINE_UPLOAD`（Phase 3 上报开关，默认关）+ `hub_enabled`。
- `backend/hub_client.py`（新）：`verify_token(token)`→account｜None，**guarded、从不抛**（未接/不可达/非 200 → None）。
- `backend/storage/db.py`：`upsert_external_user`（Hub 账号镜像进本地 users，无口令）+ `cache_token`（已校验 token 缓存进 auth_tokens，后续走本地）。
- `backend/auth/deps.py`：`resolve_via_hub`（本地未命中 → 问 Hub → 镜像+缓存）；`resolve_token_to_user_id` 保持纯本地。
- `backend/auth/middleware.py`：本地缓存命中即返回；未命中且已接 Hub → **`anyio.to_thread` 把阻塞的 Hub 校验丢工作线程**（不占事件循环，WB-002）。无 token / 未接 Hub → 回退 `LOCAL_USER_ID`。
- 验证：py_compile；隔离 backend + live hub E2E **14 项全过**（离线守卫、Hub token 校验+镜像+缓存+幂等、坏 token 回退、本地 token 路径不变）。**HUB_URL 空 = 零行为变化**，现有单机/离线照旧。

### Phase 2 —— 下行 pull（项目/成员镜像）（✅ 完成并验证，2026-07-07）
- `projects` 加 `origin`('local'|'hub')（CREATE + `_migrate` 幂等补列 + `Project.origin` 字段 + `_row_to_project`）。
- `hub_client`：`list_projects(token)` / `list_project_members(token,pid)`（guarded）。
- `storage/db.py`：`mirror_hub_project`（幂等 upsert，origin='hub'）+ `replace_hub_project_members`（清旧重建，成员账号镜像进 users）。
- `backend/hub_sync.py`（新）：`pull(token)` —— 拉该账号 Hub 项目 + 成员，幂等镜像进本地。
- `backend/routers/hub.py`（新）：`POST /api/hub/pull`（同步路由=线程池，阻塞 Hub 调用不占事件循环）、`GET /api/hub/status`；`main.py` 挂载。
- **访问控制不改**：Hub 项目/成员落进**同一批** `projects`/`project_members` 表，owner/成员按 Hub 侧 id 对齐（与鉴权桥镜像的账号 id 一致），故 WB-050 的 `project_access_role` 自动认镜像项目。
- 验证：py_compile；隔离 backend × live hub **两账号 E2E 15 项全过**（A 建共享项目+邀 B→B pull 到 origin='hub' 镜像+得 Member 访问；A-only 项目不泄漏给 B；access 读镜像；幂等无重复；owner/成员名解析；镜像 payload 无凭据字段）；origin 迁移在真库副本安全（6 项目原样、全 origin='local'）。

### Phase 3 —— 上行 outbox（执行产出回传）+ Hub 接收端点（✅ 完成并验证，2026-07-07）
- **Hub 侧**：`hub/db.py` `timeline_events` 表（(project_id, ext_id) 唯一 → 去重）+ `add_timeline_event`/`list_timeline`；`hub/routers/timeline.py` `POST/GET /api/projects/{id}/timeline`（access-gated：非成员既不能上报也不能读）；`main.py` 挂载。只存元数据 + 短摘要。
- **本地侧**：`outbox` 表（幂等入队 + synced/tries）+ `hub_identities`(user→Hub token) 表；`auth/deps.resolve_via_hub` 顺手 `set_hub_identity`（供后台 worker 以本人身份推）；`hub_client.post_timeline`；`hub_sync.enqueue_timeline_event`（**仅 Hub 镜像项目 + 开了上报开关才入队；只放 title/summary/ext_id，无正文/凭据**）+ `flush_outbox`（用各 actor 的 Hub token 推，成功标 synced、失败留待下轮）。
- **触发**：项目会话完成 → `routers/chat.py` 入队（guarded，非致命）；`routers/hub.py` 的 `/hub/pull` 顺手 flush；`agent/scheduler.py` 每 20s 后台 flush（`asyncio.to_thread` offload，不占事件循环）——断网恢复自动补传。
- **隐私**：`HUB_TIMELINE_UPLOAD` 默认**关**（执行产出默认不上云）；payload 无 LLM 凭据/连接器 secret/工作区文件（铁律 4/11）。
- 验证：py_compile（两端）；隔离 backend × live hub E2E **16 项全过**——身份存储、上报开关门控入队、离线留 pending/在线补推、**队友 B 读到 A 的时间线事件（动态署名）**、payload 无凭据字段、(project,ext_id) 去重、非成员 404。

## 处理记录（2026-07-07）

WB-062 分三期全部完成并验证（本地 backend 接 Hub：鉴权桥 → 下行 pull → 上行 outbox）。铁律对齐：
`HUB_URL` 空 = 纯本地零变化；Hub 不可达一律回退本地；同步 payload 绝不含凭据/工作区文件；团队时间线上报默认关。
详见上「实现分期与进度」三节。commit：Phase 1 `6d60ef8` · Phase 2 `ac2da4e` · Phase 3（见下）。
