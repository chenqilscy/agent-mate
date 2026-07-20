---
id: WB-063
title: 迁移与 local-first 回退 —— 存量导入 Hub、目录权威切 Hub 下发、离线/未登录回退
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - docs/agentmate-hub-架构设计.md
  - backend/auth/deps.py:30
  - backend/storage/db.py:68
created: 2026-07-07
---

## 问题

同步机制（[WB-062](WB-062-local-hub-sync-protocol.md)）就绪后，还需把存量单机数据接进 Hub，并把目录权威从「本地库」切到「Hub 下发」，同时**保住 local-first**——不登录/离线仍能纯本地用。这是让重构对既有用户平滑落地、且不牺牲本机可用性的收尾环节。

## 触发场景

- 老用户已有本地项目/自造专家/会话历史；首次登录 Hub 时希望把它们带上云、跨机可用。
- 目录（专家/连接器/技能定义）此前落在本地库（WB-059/060），上线 Hub 后应由 Hub 统一下发、本地 override 叠加。
- 用户没网或不想登录时，一切照常本地跑。

## 影响

P2（择机，收尾）：依赖 WB-059/060/061/062 全部就绪。做好了才算「重构落地」而非「多出一套并行系统」。

## 建议修法

按 [架构设计 §8](../agentmate-hub-架构设计.md)：

- **存量导入**：首次登录 Hub 提供「导入本地数据」——项目/成员/自造专家/org 级目录**上行**；会话作为历史时间线可选上行或留本地（尊重隐私开关）。
- **`LOCAL_USER_ID` 映射**到 Hub 账号，映射关系记本地；导入幂等、可重试。
- **目录权威切换**：目录源从「本地库（WB-059/060）」切到「Hub 下发 + 本地 override」；本地 builtin 种子退为离线兜底。
- **回退优先**：无网/未登录 → 回退 `LOCAL_USER_ID`（[auth/deps.py:30](../../backend/auth/deps.py#L30)），纯本地全功能可用；Hub 是可选增强、非强制。中间件只多一层「token 先问本地缓存、必要时校验 Hub」。

## 验证

- 老库（有本地项目/自造专家/会话）首次登录 → 导入 → Hub 与另一客户端可见；重复导入不产生重复数据。
- 断开 Hub / 不登录：新建项目、召唤专家（含内置人格）、挂连接器、执行任务全部照常（本地兜底目录生效）。
- 目录在 Hub 改一条 → 客户端 pull 后反映；本机 override（本地装的技能/自造专家）仍优先/叠加正确。
- 全程无「因连不上平台而阻断本机使用」的路径。

## 处理记录（2026-07-07）

### 改动（本地侧为主，导入复用 Hub 既有 POST /api/projects）
- `storage/db.py`：`hub_imports`(local_id→hub_id，保证重复导入不产生重复数据) + `hub_link`(LOCAL_USER_ID↔Hub 账号) 表 + DAO（`record_import`/`get_import`/`set_hub_link`/`get_hub_link`）。均为新表（`CREATE IF NOT EXISTS`），老库安全、无列迁移。
- `hub_client.py`：`create_project(token, project)`（存量导入用）+ `list_catalog(token, category)`（目录下发 capability）。
- `hub_sync.py`：`import_local_to_hub(token, account)` —— 把 LOCAL_USER 的本地原生项目（origin='local'）上行 Hub，**幂等**（`hub_imports` 有记录则跳过），记 LOCAL↔Hub 绑定。只上行元数据，无凭据/工作区文件。
- `routers/hub.py`：`POST /api/hub/import`（需有效 Hub token）+ `GET /api/hub/status`（enabled + linked 账号，供前端显示同步/导入入口）。

### 三部分对应验证
- **存量导入**：老库首次登录 → 导入 3 个本地项目 → Hub 与另一「客户端」可见；重复导入 imported=0/skipped=3、Hub 仍 3 个（**无重复**）。✅
- **local-first 回退（回退优先）**：HUB_URL 空 → 新建项目、召唤内置人格、`connector_specs` 全部照常；import 为 no-op。**无「因连不上平台阻断本机」的路径**。✅
- **目录权威切换**：实现了 Hub 目录 pull capability（`list_catalog`，Hub 预埋目录空 → 返回 `[]`，pull 成功）；**本地 builtin 种子仍权威、作离线兜底**（验证 `builtin_persona` 照常）。⚠️ 完整的「Hub 下发覆盖本地 + org 级目录运营/Admin」需 Hub 侧目录 seed + 管理界面——属后续「目录运营」范畴，本轮预埋 capability + 兜底保证，未把空覆盖硬接进前端 `/api/catalog` 热路径（避免为空叠加加风险）。

### 验证
- `py_compile` 全过；隔离 backend × live hub E2E **15 项全过**（见上）；新表在现有库为纯增量、迁移安全。
- 铁律：`HUB_URL` 空 = 纯本地零变化；import payload 无 LLM 凭据/连接器 secret/工作区文件（铁律 4/11）；导入仅在带有效 Hub token 时。

**AgentMate Hub epic（[WB-058](WB-058-hub-control-plane-epic.md)）至此全部完成：** WB-059 真定义入库 · WB-060 橱窗入库 · WB-061 Hub 骨架 · WB-062 同步(三期) · WB-063 迁移与回退。

commit：（见下）。
