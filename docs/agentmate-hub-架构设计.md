# AgentMate Hub —— 架构设计（local-first 执行 + 云端控制平面）

> 状态：设计稿 v1 · 2026-07-07 · 对应 epic [WB-058](issues/WB-058-hub-control-plane-epic.md)
> 关联：[实现方案](agentmate-实现方案.md) · [CLAUDE.md](../CLAUDE.md)

本文是「专家/技能/连接器定义入库」与「多用户协作管理平台」两项重构的总设计，
供动手前对齐。**只定方向与数据/协议边界，不写实现代码**；具体落地拆到 WB-059～WB-063。

---

## 1. 背景与要解决的问题

AgentMate 现在是纯 **local-first**：后端跑在用户本机 `localhost:8000`，浏览器只是显示器。
M7「协作」是靠**「共享后端即 Hub」**实现的——多个用户其实都指向**某一台机器**的后端
（身份、项目、成员都躺在那台机器的 SQLite 里）。这带来两个结构性问题：

1. **协作撑不起团队**：靠一台个人机在线才能协作；身份/项目/成员是每台机器各一份 SQLite，
   无中心权威源，谈不上真正的多人、多设备、跨机协作。（用户反馈 #2）
2. **能力定义半硬编码**：专家/技能/连接器的「定义」散在代码里，无法集中管理、运营、下发。（用户反馈 #1）
   - 内置专家人格 13 条：[backend/agent/experts.py:9](../backend/agent/experts.py#L9)（`EXPERTS` 字典，注入系统提示、真生效）
   - 连接器启动注册表 6 个：[backend/agent/mcp_client.py:70](../backend/agent/mcp_client.py#L70)（`CONNECTORS`，真接入 MCP）
   - 纯静态「橱窗目录」：[src/data/catalog.ts](../src/data/catalog.ts)（`EXP_GRID`/`EXP_TEAMS`/`SK_GRID`/`SKILLHUB_*`/`CONNS`/`CONN_META`/模板/灵感……绝大多数只是可浏览商品卡，未接真实能力）

> 已经动态的部分（**不在本次重构范围内的「已解决」**）：自定义专家（`experts` 表，owner 维度，WB-049）、
> 已安装技能（磁盘 `~/.agentmate/skills/` + SkillHub CLI 真安装/搜索）、项目/会话/消息/待办/自动化/用户/成员/通知（SQLite）。

**结论方向**：立一个独立的中心服务 **AgentMate Hub**（控制平面），掌管账号/组织/项目/成员/目录；
本地客户端只管**执行**并与 Hub **同步**。#1 是 #2 的一部分——目录就住在 Hub 库里，下发给客户端。

---

## 2. 目标与非目标

### 目标
- **G1** 立 Hub 中心服务，作为身份/组织/项目/成员/邀请/目录的**权威源（source of truth）**。
- **G2** 本地客户端保留 local-first 执行内核（agent 循环、沙箱、LLM 调用、凭据留本地），与 Hub 同步。
- **G3** 专家/技能/连接器的**真定义 + 橱窗目录**统一入库、可管理、可由 Hub 下发。
- **G4** 平滑迁移：单机存量数据可导入 Hub；未登录/离线仍能纯本地用（local-first 不丢）。

### 非目标（本轮不做）
- 不把 **LLM 凭据 / 沙箱工作区文件**上云（铁律 4；执行与私密数据留本地）。
- 不做实时通道（在线状态/评论/@提及的实时推送）——同步先做**拉取 + 异步回传**，实时另立里程碑。
- 不做计费/套餐、不做 SaaS 多区域部署——Hub 先做成**可自托管的单体服务**，SaaS 后续。

---

## 3. 总体架构：两个平面

```
┌─────────────────────────── 控制平面（AgentMate Hub · 中心服务）──────────────────────────┐
│  权威源：账号 / 组织·团队 / 项目·成员·角色·邀请 / 目录（专家·技能·连接器定义 + 橱窗）        │
│  鉴权：签发 token   ·   团队时间线（执行产出的只读聚合）                                     │
│  部署：独立服务（FastAPI + 库），可自托管                                                    │
└───────────────▲───────────────────────────────────────────────▲────────────────────────┘
     下行 pull  │ 身份/项目/成员/目录（增量、版本化）      上行 push │ 执行产出（会话/消息/待办/运行记录）
                │                                                   │
┌───────────────┴───────────────────────────────────────────────┴────────────────────────┐
│  执行平面（本地客户端 = 现有 backend + 前端 + Tauri 外壳）                                   │
│  agent 工具循环 · 沙箱工作区 · run_command · MCP 连接器 spawn · LLM 凭据(backend/.env)       │
│  本地 SQLite：Hub 数据的镜像缓存(read-only) + 执行产出(权威) + outbox(待回传)                │
│  离线/未登录 → 降级为纯本地 owner（local-first fallback）                                    │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- 本地 backend 对 **Hub 是客户端**（带 token 调 Hub API）；对**前端仍是服务端**（现有 `/api` 不变形态）。
- 前端不直接连 Hub——统一走本地 backend，由本地 backend 做同步与缓存。这样离线/内网也能跑，且不暴露 Hub 细节给浏览器。

---

## 4. 数据归属划分（哪些数据、权威在哪）

| 数据 | 权威源 | 本地存 | 同步方向 | 备注 |
|---|---|---|---|---|
| 账号 / 组织·团队 | **Hub** | 镜像缓存 | 下行 | Hub 签发 token |
| 项目元数据 + 成员/角色/邀请 | **Hub** | 镜像缓存 | 下行 | 本地按缓存成员表做访问控制 |
| 目录：专家/技能/连接器**定义 + 橱窗** | **Hub** | 镜像缓存/下发 | 下行 | #1；本地可叠加本机 override（本地装的技能/自造专家） |
| 会话 / 消息 / trace | **本地** | 权威 | 上行(append) | 回传 Hub 供团队时间线（只读镜像，Hub 不改） |
| 待办 / 工作项 | 本地写 | 权威→同步 | 双向 | 先本地权威 + 上行；双向冲突用 `updated_at` LWW |
| 运行记录 / 自动化 | **本地** | 权威 | 上行 | |
| LLM 凭据（`LLM_API_KEY`…） | **本地 only** | 权威 | 不同步 | 铁律 4，绝不上云 |
| 沙箱工作区文件 | **本地 only** | 权威 | 不同步 | 大文件/私密不上云；只上报「装了什么技能」等元数据 |
| 已安装技能（磁盘） | 本地 | 权威 | 上行元数据 | 目录定义在 Hub，**安装动作**仍本地（SkillHub CLI） |

**原则**：控制平面数据 **Hub 下行覆盖**本地镜像；执行产出**本地权威、上行 append**；
凭据与工作区文件**永不上云**。

---

## 5. 目录数据模型（#1：定义 + 橱窗统一入库）

核心决定：**一张表既是「可浏览橱窗目录」又是「真生效定义」**，用字段区分真接入 vs 纯展示卡，
避免「真定义」和「橱窗」两套割裂。分四类目录表（草案，字段以设计意图为准，落地时再定精确列）：

```
catalog_experts          -- 专家人格（并入现有 experts 表：自造专家 = scope 'user'）
  id, slug, name, subtitle, avatar, intro, persona, tags[],
  category, badge, source,
  functional  bool,       -- persona 是否真注入生效（真定义） vs 纯橱窗卡
  scope       enum,       -- 'builtin' | 'org' | 'user'
  org_id, owner_id,       -- 归属（builtin 为空）
  enabled, sort, version, created_at, updated_at

catalog_expert_teams     -- 专家团（EXP_TEAMS）
  id, slug, name, source, badge, intro, strengths[], members[](json), prompts[],
  category, tags[], scope, org_id, enabled, sort, version, ...

catalog_connectors       -- 连接器定义（并入 mcp_client.CONNECTORS 的启动 spec + CONN_META 橱窗）
  id, slug, name, icon, description, full_desc, setup, oauth bool,
  status     enum,        -- 'rdy'(内置即用) | 'tok'(需凭据) | 'catalog'(未接入橱窗卡)
  launch     json,        -- 启动 spec：builtin_server / command+args / secret_env / requires（对应 CONNECTORS）
  tools[](json), prompts[], requires[], category,
  scope, org_id, enabled, sort, version, ...

catalog_skills           -- 技能橱窗目录（SK_GRID/SKILLHUB_*）；已安装技能仍在磁盘，这里是可浏览目录 + SkillHub 元数据
  id, slug, name, label, color, description, category,
  downloads, stars, badge, source, featured bool, kit_id,
  scope, org_id, enabled, sort, version, ...

-- 附：catalog_automation_templates(AUTO) / catalog_inspirations(INSP) / catalog_project_templates(NP_TPLS)
```

要点：
- **真定义 vs 橱窗**靠 `functional`（专家 persona 是否注入）/ `status`+`launch`（连接器是否真接入 MCP）区分，
  同一张表内并存。橱窗卡 = `functional=false` / `status='catalog'`，不接真实能力（与现状一致）。
- **`scope` + `version`** 为 Hub 下发/多租户预埋：`builtin` 由 Hub 运营下发、`org` 由团队管理员维护、`user` 是个人自造。
  P0 阶段先都落**本地 backend 的库**（现有 SQLite），作为将来 Hub 目录的雏形；P3 再把权威切到 Hub 下发。
- **兼容现状**：现有 `experts` 表（WB-049 自造专家）并入 `catalog_experts`（`scope='user'`, `functional=true`），
  运行时人格解析（[runtime.py:236](../backend/agent/runtime.py#L236)）与连接器解析（[mcp_client.py](../backend/agent/mcp_client.py)）改**读库**，
  内置 13 人格 / 6 连接器作为 `scope='builtin'` 种子数据入库（首次启动 seed）。

---

## 6. 同步协议

### 下行 pull（身份/项目/成员/目录）
- 触发：客户端启动 + 定时 + 按需（如打开某项目）。
- 增量：每类资源带 `version`/`updated_at`，客户端传上次游标，Hub 只回变更集。
- 落地：写本地**镜像表**（`origin='hub'`, 视为 read-only）；本地 override 层（本机技能/自造专家）叠加在镜像之上。

### 上行 push（执行产出）—— outbox 模式
- 本地执行先落本地库并写一条 **outbox** 记录（待同步）。
- 后台 worker 批量推 Hub；确认后标记已同步；断线/离线自动重连补推（保证 local-first 可离线）。
- 语义：会话/消息/运行记录 **append-only**（Hub 侧只读镜像，供团队时间线）；待办双向用 `updated_at` LWW。

### 冲突与一致性
- 控制平面：**Hub 权威**，下行覆盖本地镜像。
- 执行产出：**本地权威**，上行 append，Hub 不回改。
- 双向（待办）：`updated_at` last-write-wins，先简单；将来需要再上 CRDT/版本向量。

---

## 7. 鉴权演进

- **现状**：本地 backend 自存 `users`/`auth_tokens`，无 token → `LOCAL_USER_ID`
  （[auth/deps.py:30](../backend/auth/deps.py#L30)、[auth/middleware.py](../backend/auth/middleware.py)）。
- **目标**：账号权威在 Hub。本地「登录」= 走 Hub 拿 token，本地缓存身份；
  本地 backend 用该 token 作为**客户端**调 Hub。对前端仍沿用现有 Bearer 机制不变。
- **回退**：无网/未登录 → 仍回退 `LOCAL_USER_ID`，纯本地可用（local-first 不破）。中间件只多一层「token 先问本地缓存、必要时校验 Hub」。

---

## 8. 迁移路径（存量单机 → Hub + 本地）

1. **目录先行**（不依赖 Hub）：内置人格/连接器注册表 + `catalog.ts` 橱窗 → 迁到**本地 backend 库**（WB-059/060）。
   此步纯本地即可交付、可独立验证，是 Hub 目录的雏形。
2. **首次登录 Hub**：提供「导入本地数据到 Hub」——项目/成员/自造专家/目录（org 级）上行；会话作为历史时间线可选上行或留本地。
3. **`LOCAL_USER_ID` 映射**到 Hub 账号；映射关系记本地。
4. **目录权威切换**：把目录源从「本地库」切到「Hub 下发 + 本地 override」（WB-063）。
5. 全程保留**纯本地模式**（不登录也能用），Hub 是可选增强，非强制。

---

## 9. 部署形态

- **代码组织（monorepo，本仓库内）**：Hub 作为**独立服务但同仓**，放在本仓库新目录 **`hub/`**，与本地 `backend/`
  代码解耦、可单独部署与启动。共享一份 git 历史、便于同步演进协议改动；不另起仓库。
  - 可抽出的公共部分（如 `Role` 枚举、目录/成员的数据契约）后续按需提取到共享模块，避免 `hub/` 与 `backend/` 各写一份漂移。
- **Hub 运行形态**：技术栈沿用 FastAPI；库先 SQLite 亦可，规模上来换 Postgres。
  先做成**可自托管的单体服务**；SaaS（托管注册即用）后续，多租户已由 `org_id`/`scope` 预埋。
- **本地客户端**：现有 Tauri 外壳 + `backend/` + 前端形态不变，新增「连接 Hub」配置（Hub 地址 + 登录）。

---

## 10. 里程碑与 issue 映射

| 阶段 | 内容 | Issue | 依赖 |
|---|---|---|---|
| **总纲** | 本设计 + 方向对齐 | [WB-058](issues/WB-058-hub-control-plane-epic.md) | — |
| **P0-a** | 目录「真定义」入库（内置人格 + 连接器注册表 → 库，运行时改读库） | [WB-059](issues/WB-059-catalog-definitions-to-db.md) | — |
| **P0-b** | 橱窗目录入库（`catalog.ts` 静态卡 → 库 + API，前端改从接口取） | [WB-060](issues/WB-060-catalog-showcase-to-db.md) | WB-059 |
| **P1** | Hub 服务骨架（账号/组织/项目/成员/邀请权威源 + 鉴权签发） | [WB-061](issues/WB-061-hub-service-skeleton.md) | — |
| **P2** | 本地 ⇄ Hub 同步协议（下行拉取 + 上行 outbox 回传 + 增量） | [WB-062](issues/WB-062-local-hub-sync-protocol.md) | WB-061 |
| **P3** | 迁移与 local-first 回退（存量导入、目录权威切 Hub、离线回退） | [WB-063](issues/WB-063-hub-migration-and-local-fallback.md) | WB-059/060/061/062 |

> P0（WB-059/060）可**先独立交付**，不依赖 Hub——先把定义/橱窗在本地库跑通，再谈中心化。

---

## 11. 风险与铁律对齐

- **铁律 1（不硬编码不模拟）**：目录入库后，内置人格/连接器作为**真种子数据**入库，运行时读库真生效；橱窗卡沿用现状（明确是展示、不接真实能力），不伪造授权。
- **铁律 4（凭据只在后端）**：Hub 同步**绝不上传** `LLM_API_KEY` 与连接器 secret；这些永远只在本地 `backend/.env`。
- **铁律 5（SSE 契约）**：同步/目录变化若要反映到 UI，走既有事件/刷新机制，一种事件 ⇄ 一种 UI 形态。
- **数据隐私**：会话/工作区可能含敏感内容——上行团队时间线需**可配置**（项目/用户级开关），默认最小上报。
- **回退优先**：任何 Hub 不可用场景都必须降级为本地可用，绝不因「连不上平台」阻断本机使用。
