---
id: WB-184
title: 技能浏览面板四套数据源 + 两套分类体系并存 —— 收敛为一个面板一套分类
severity: P2
area: frontend
status: in-progress
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:337
  - src/views/ExpertsView.tsx:427
  - src/views/ExpertsView.tsx:473
  - src/views/ExpertsView.tsx:463
  - src/stores/catalogStore.ts:100
  - src/stores/catalogStore.ts:125
  - src/data/catalog.ts:101
created: 2026-07-16
---

## 问题

一个技能面板里摞了**四套来源不同、质量不等的数据**，外加**两套互不相干的分类体系**：

| 段 | 组件 | 数据源 | 兜底层数 |
|---|---|---|---|
| 精选技能 | `FeaturedSkills` L337 | Hub `SKILLHUB_FEATURED` 下发 → 静态 `SKILLHUB_FEATURED` | 2 |
| 推荐 | `RecoView` L473 | `/api/catalog` → `catalog_showcase` 表（内容仍是静态 `SK_GRID`） | 1 |
| SkillHub | `SkillHubView` L427 | Hub 镜像 → `/skills/rankings`（真实）→ 静态 `SKILLHUB_GRID` | **3** |
| 套件 | `KitView` L495 | 纯静态（见 WB-182） | 0 |

**概念重叠且质量倒挂**：「推荐」和「SkillHub」都是"可浏览的技能列表"，但推荐段的卡
（`.scard`）**没有安装按钮、没有详情入口、没有已装态**，＋ 号还是假的（WB-181）；
SkillHub 段的卡（`.hcard`）才是全功能的。用户看到两段外观相似、能力天差地别的列表。

**两套分类**：推荐段用 `SK_CATS`（14 项），SkillHub 段用 `SKILLHUB_CATS`（13 项）——
**完全不同的分类体系上下并排**在同一面板。且静态兜底态下 `SKILLHUB_GRID` 实际只覆盖 7 个分类，
点「教育学习」「行业专业」**必然空白**（L467「该分类下暂无技能」）。

**兜底链竞态**（`catalogStore.ts:125-129`）：启动串行跑 `load()` → `syncFromHub()` → `fallbackToRankings()`。
`fallbackToRankings` 用 `skillMirror.length > 0` 跳过（L100），但 `syncFromHub` 仅在 `r.catalog > 0`
时重载（L92）—— **若 Hub 已连但本次 pull 无新目录，`skillMirror` 保持空，会被 rankings 覆盖**。
用户看到的"SkillHub"内容取决于启动时序。

**死代码**：`SK_RECO`（`catalog.ts:101-106`）前端**零消费**（仅存在于 `catalogStore` 的类型与 FALLBACK 中）。

## 触发场景

- 技能页 → 「推荐」段点某卡 → 无反应（无详情弹窗）；同一技能在「SkillHub」段点 → 有详情、能装。
- 静态兜底态（未连 Hub 且无 CLI）→ SkillHub 段点分类「教育学习」→ 永远空白。
- 连了 Hub 但某次 pull 无新目录 → 刷新几次，「SkillHub」段内容在镜像与 rankings 之间跳变。

## 影响

P2。不阻塞功能，但这是"橱窗"侧复杂度失控的集中体现：四套源三层兜底，
维护者与用户都无法预期某一刻看到的是什么。也是 WB-181 假交互与 WB-179 假技能的温床。

## 建议修法

1. **合并「推荐」与「SkillHub」为一个浏览面板**，统一用全功能富卡片（`.hcard`，带安装/详情/已装态）；
   「推荐」若要保留语义，降为该面板的一个**排序/筛选档**（接 `rankings?type=recommended`，后端已支持）。
2. **一套分类**：以 Hub 下发的 `skill-category`（SkillHub 12 场景）为准；
   删掉 `SK_CATS`；分类 chip 按 `count > 0` 动态生成（L446 已有此逻辑，推广到兜底态）。
3. **兜底链去竞态**：改为「镜像为空 → 才跑 rankings」的单一判定，且在 `syncFromHub` 完成后
   （而非按 `r.catalog > 0`）重新求值；或干脆串成一个 `resolveSkillCatalog()`。
4. **删静态假数据**：`SKILLHUB_GRID` 39 条（含写死 downloads/stars）、`SK_RECO`（死代码）、
   `SK_CATS`；与 WB-183 的孤儿清理一并做。
5. 沿用既有 class 与 token（`.hcard` / `.cathead` / `.sk-sort` …），不新增样式（铁律#2）。

## 验证

- `npx tsc --noEmit` 过。
- 三态实测（连 Hub / 未连 Hub 有 CLI / 全离线）：每态下面板内容来源可预期，**无静态假数据出现**；
  分类 chip 点任意一个都有内容或诚实空态。
- 反复刷新 10 次（连 Hub 态），SkillHub 段内容稳定，不在镜像/rankings 间跳变。
- 明暗双主题都看。

## 处理记录（2026-07-17）· 第一刀：清掉「我们自己的目录」里的假数据

### ⚠️ 本条原写的修法第 1 条（合并推荐与 SkillHub）经查**不能照做**

原文说「概念重叠」「推荐段的卡没有安装按钮、没有详情入口、没有已装态」。查证后两点都变了：

1. **「质量倒挂」已被 WB-181 修掉**：推荐段的 ＋ 现在按真实身份分派（内置→挂载进会话、
   其余→真安装），不再是假按钮。
2. **两段不是概念重叠，是两个不同的数据源**——这一点 WB-060 在 `db.py` 里立过架构原则：
   > 功能定义(专家人格/连接器 spec) 在 catalog_experts/catalog_connectors(WB-059)，
   > 此表只装纯浏览卡——**职责分离**

   即：**「推荐」= 我们自己的目录**（`catalog_showcase.SK_GRID`，Manager 可 CRUD 运营）；
   **「SkillHub」= 上游 skillhub.cn 商店的镜像**（369 条，见并发会话的 WB-191）。
   这个划分是**对的**，不该合并。
3. **爆炸半径**：`SK_GRID` 还被 Manager 的目录管理 CRUD（`CFG_CATS.skills`）、WB-080 的门户
   项目配置 picker、3 处图标反查消费。把推荐段改读 `catalog_skills` 会同时违反职责分离
   **并**打断这几条链路。

故**放弃「合并」**，改做本条真正有价值的那部分：**清掉这一段里的假数据**。

### ✅ 删 7 张虚构卡（SK_GRID 16 → 9）

WB-181 摸底时实测过：这 16 张是三种东西混在一起。其中 **7 张上游根本不存在** ——
逐个搜上游确认（搜任何一个中文名都只回 `self-improving-agent`/`find-skills`/`summarize`
这几个通用结果），点它们的安装必然「SkillHub 未找到「X」」：

`NeoData金融搜索服务` / `A股全栈数据` / `QQ音乐助手` / `IMAP/SMTP邮件` /
`fbs-bookwriter` / `QQ邮箱` / `创业可以学`

给不存在的商品挂橱窗卡就是模拟（铁律#1）。剩下 **9 张全是真的**：6 张内置技能
（定义在 `catalog_skills`，WB-183）+ 3 张名字能精确解析到真 slug
（`腾讯自选股-金融数据查询`→`westock-data` / `skill-creator` / `腾讯新闻`→`tencent-news`）。

### ✅ 删 SK_RECO（死代码）

全仓库只有「定义 + `catalogStore` 的类型/兜底各一处」引用，**前端从未渲染**
（原型 `workbuddy-v2.html:1361` 用过，React 版没搬）。

### 三层同步（照并发会话 WB-190 立的方法）

`catalog.ts` → `catalog_showcase.json` → 运行库（**按名对账 DELETE + sort 重排**——
`_seed_catalog` 是「缺失才插」，删了 JSON 库里旧行不会自己消失）。

### 验证（14 项静态/DB + 9 项 CDP，全过）

- **层间一致性**：从 `catalog.ts` **真抽取**（不手写期望值）与种子 JSON 逐字比对相等；
  运行库 9 行且顺序与 `catalog.ts` 一致；`SK_RECO` 三层皆无。
- **复活陷阱**：全新空库连跑两次真 `init_db()` → SK_GRID **seed 出 9 条（不是 16）**、
  虚构卡命中 0、SK_RECO 0 行、WB-183 的 `catalog_skills` 照常 6 条。
- **真 API**（硬重启后端）：`GET /api/catalog` → SK_GRID 9 条无虚构卡、响应里无 SK_RECO；
  `GET /api/skills/builtin` → 6 条读库正常。
- **CDP 实测明暗双主题**：推荐段各 9 张卡、7 张虚构卡全消失、6 张内置仍「挂载到本会话」/
  3 张可装仍「安装」；**SkillHub 段未被误伤**（仍 369 张）。

**测试自身踩的坑**：首版用 `shutil.copy(DB_PATH)` 做库副本验重种陷阱，副本里 SK_GRID=**17**
（WB-190 改动**之前**的状态）——因为库是 **WAL 模式**，改动还在 `-wal` 里没检查点，
只拷主 `.db` 得到的是过时快照。改用「全新空库全量 seed」验证（seed 源是 JSON，JSON 已改）。

### 待做（本条保持 in-progress）

| 项 | 状态 |
|---|---|
| 修法 1 合并推荐/SkillHub | ⛔ **不做**（经查违反 WB-060 的职责分离，理由见上） |
| 修法 2 一套分类（删 SK_CATS、按 count>0 动态生成） | ⬜ 待做；`SK_GRID` 的 `[icon,name,desc]` 仍无 category 字段 → **WB-195** 仍被阻塞，需 `catalog_skills.category`（列已建）+ 让推荐段拿到它 |
| 修法 3 兜底链去竞态 | ⛔ **不做 —— 经查竞态不存在（本条原文写错了）**，见下 |
| 修法 4 删 `SKILLHUB_GRID` 37 条静态假 downloads/stars | ⬜ 待做；它是**未接 Hub/离线时**的兜底，删了要给诚实空态（与 WB-071 的 rankings 兜底一起想） |
| 修法 4 删 `SK_RECO` | ✅ 本次 |
| 修法 4 删 `SK_CATS` | ⬜ 随修法 2 |

### ⛔ 修法 3「兜底链竞态」经查不成立 —— 本条原文写错了

原文断言：「`fallbackToRankings` 用 `skillMirror.length > 0` 判断是否跳过，但 `hubPulled` 是
模块级 flag，且 `syncFromHub` 仅在 `r.catalog > 0` 时重载 —— 若 Hub 已连但本次 pull 无新目录，
`skillMirror` 保持空，会被 rankings 覆盖成排行数据，用户看到的内容取决于启动时序。」

逐条核实后**三点都不成立**：

1. **没有并发 → 谈不上竞态**。`catalogStore.ts:125-129` 的链条是 `await` 串行的；
   `load()` 全仓库只有 2 个调用点（L92 `syncFromHub` 内、L126 IIFE），都在这条链上；
   `skillMirror` 只有 2 个写入点（L76 `load` 的 `set`、L114 `fallbackToRankings` 的 `setState`），
   同样都在链上；模块级 IIFE 只有 1 个。**没有并发写者**。
2. **「Hub 已连但 pull 无新目录 → mirror 空 → 被 rankings 填充」正是 WB-071 设计的分层**
   （Hub 镜像 → 真实 rankings → 静态兜底），是**期望行为**，不是覆盖事故。
3. **「取决于启动时序」不对**：链条确定性 await，无时序依赖。

另查了一条疑似路径也不成立：`hubStore.connect`（连接 Hub）确实另跑一次 `api.hubPull()` 且
**不**重载 catalogStore —— 但它下一行是 `window.location.reload()`（`hubStore.ts:37`），
整个应用重载、`catalogStore` 的 IIFE 重跑，故镜像照常进。

写这条时我是照着代码形状猜的（看到 check-then-act + 模块级 flag 就下了结论），没推演场景。
**不改代码**。

- commit：未提交（待用户确认）。
