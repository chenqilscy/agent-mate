---
id: WB-176
title: 精简专家/专家团橱窗数据 —— 三层数据源同步裁剪，只留常用少量
severity: P3
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/data/catalog.ts:19
  - src/data/catalog.ts:28
  - src/data/catalog.ts:31
  - src/data/catalog.ts:66
  - backend/storage/catalog_showcase.json
  - backend/storage/db.py:677
  - backend/agentmate.db
created: 2026-07-16
---

## 问题

「专家·技能·连接器 → 专家」页堆了过多目录数据，用户诉求是「不需要这么多专家数据」。
当前量级（`backend/agentmate.db` 表 `catalog_showcase`）：

| kind | 现状 | 说明 |
| --- | --- | --- |
| `EXP_SCENES` | 6 | 精选场景卡 |
| `EXP_GRID` | 16 | 专家卡 |
| `EXP_TEAMS` | 8 | 专家团卡 |
| `EXP_CATS` | 15 | 分类标签 |

这不是 bug 而是**目录数据体量**问题，但改法上有两个真陷阱，必须按数据分层同时处理，否则「删了会复活」：

1. **种子按 kind 查重会整批重种**：[`db.py:677-690`](../../backend/storage/db.py#L677-L690) 的 `_seed_showcase` 逻辑是
   「某 kind 已有行则跳过」。若把某 kind 删空，下次启动就从 `backend/storage/catalog_showcase.json`
   把整批种子重新种回来。
2. **前端静态兜底会顶上来**：[`catalogStore.ts:66`](../../src/stores/catalogStore.ts#L66) 是
   `if (raw[k] === undefined) continue // 后端未提供某项 → 保留兜底`。而 `showcase_all`
   （[`db.py:1412`](../../backend/storage/db.py#L1412)）按行聚合，某 kind 无行则该键**不出现**在响应里
   → 前端退回 `src/data/catalog.ts` 里硬编码的 16 个专家。

即：数据有**三层**（前端静态兜底 `src/data/catalog.ts` → 后端种子 `catalog_showcase.json` → 运行库
`agentmate.db`），只改一层都不是真裁剪。

## 触发场景

1. 打开 App →「专家·技能·连接器」→「专家」tab → 精选场景 6 张、专家 16 张、专家团 8 张、分类 15 个。
2. 若只 `DELETE FROM catalog_showcase WHERE kind='EXP_GRID'` 并重启后端 → 16 个专家**原样复活**（陷阱 1）。
3. 若只删库不改 `src/data/catalog.ts`，且该 kind 被删空 → API 不返回该键 → 前端**仍显示 16 个**（陷阱 2）。

## 影响

P3：纯目录数据体量/信噪比问题，不影响功能正确性，也不影响运行时 persona 解析。
但踩中上述任一陷阱会导致「改了没生效」，白白浪费一轮排查（本仓库「serving stale code」类坑的同族）。

## 建议修法

**范围**：只动专家橱窗四个 kind（`EXP_GRID` / `EXP_TEAMS` / `EXP_SCENES` / `EXP_CATS`）。
**不动**（用户明确划定）：

- `NP_EXPERTS`（新建项目向导的 8 个推荐专家）——另一个界面，另说。
- `catalog_experts`（13 条内置人格，运行时 `builtin_persona` 源）——保留。
  注意其种子 [`_seed_catalog`](../../backend/storage/db.py#L644) 是**按名字查重**的，删了每次启动都会复活，
  真要删得改 `storage/catalog_seed.py`；本 issue 不做。
- `experts` 表（「我的专家」用户自建）——本来就是 0 行。

**保留名单**（选取原则：优先留在 `catalog_experts` 里**有人格**的，保证留下来的专家是真能用的，
而不是只有卡片没人格的空壳）：

- 专家 16 → **7**：高级开发工程师、前端开发工程师、UI设计师、内容创作专家、
  长文档写作与改稿专家、数据分析报告师、创业伙伴（7 个全部有 persona）。
- 专家团 8 → **3**：软件开发团队、深度研究团队、产品战略团队。
- 分类 15 → **6**：全部、OPC·一人公司、产品设计、技术工程、数据智能、内容创作（按剩余专家/团的 category 收敛，保持原相对顺序）。
- 精选场景 6 → **3**：按存活实体过滤条目，条目全没的场景整张删除
  （投资分析 / 法律咨询 / 电商运营 → 删）。
  场景条目只是展示串（[`ExpertsView.tsx:76-85`](../../src/views/ExpertsView.tsx#L76-L85) 点击仅 toast + 切 tab），
  不解析实体，故过滤不会产生断链。

**三层同步改**：

1. `src/data/catalog.ts` —— `EXP_SCENES` / `EXP_CATS` / `EXP_GRID` / `EXP_TEAMS` 四段裁到保留名单（静态兜底层）。
2. `backend/storage/catalog_showcase.json` —— 同名四个 kind 裁到一致（种子层）。
3. `backend/agentmate.db` 的 `catalog_showcase` —— 删掉落选行（运行库层）。
   因每个 kind 都还留有行（≥1），`_seed_showcase` 的 kind 查重会跳过 → 不会重种。

三层内容需**逐字一致**，否则「后端断连时看到的目录」与「正常状态」不是同一份。

## 验证

1. `npx tsc --noEmit` 通过（`catalog.ts` 有元组类型标注，裁剪不能破类型）。
2. 硬重启后端（`reload=True` 有时不生效），`GET /api/catalog` 断言四个 kind 的条数为 7 / 3 / 3 / 6，
   且**重启第二次**后条数不变（证明没被 `_seed_showcase` 重种 —— 陷阱 1 的回归）。
3. 浏览器打开「专家」tab 实测：精选场景 3 张、专家 7 张、专家团 3 张、分类 6 个；
   逐个点分类做过滤，无空态误报；**明暗双主题**各看一眼（本项目铁律 3）。
4. 回归：「新建项目」向导的推荐专家仍是 8 个（证明没误伤 `NP_EXPERTS`）；
   会话里召唤保留下来的专家仍能命中人格（证明没误伤 `catalog_experts`）。

## 处理记录（2026-07-16）

### 改动（三层同步）

1. `src/data/catalog.ts`（静态兜底层）：`EXP_SCENES` 6→3、`EXP_CATS` 15→6、`EXP_GRID` 16→7、`EXP_TEAMS` 8→3。
2. `backend/storage/catalog_showcase.json`（种子层）：同名四个 kind 裁到与 ①**逐字一致**。
   改法是脚本按保留名单过滤后整份回写 —— 先验证过 `json.loads → json.dumps(ensure_ascii=False, indent=1)`
   往返与原文**逐字节相同**，故回写不会顺带重排其余 20 个 kind。
3. `backend/agentmate.db`（运行库层）：按种子对账 —— 落选行 DELETE，留存行 UPDATE（含 `sort` 重排 0..n-1，
   与 `_seed_showcase` 的 `enumerate` 语义对齐）。删除前用 sqlite backup API 备份（活动库带 WAL，直接 copy 会漏未 checkpoint 的 WAL）。

保留名单（择取原则：优先留 `catalog_experts` 里**有人格**的，保证留下的专家真能用，而非有卡无魂）：

- 专家 7：高级开发工程师、内容创作专家、创业伙伴、数据分析报告师、长文档写作与改稿专家、UI设计师、前端开发工程师（7 个全部有 persona）。
- 专家团 3：软件开发团队、深度研究团队、产品战略团队。
- 分类 6：全部、OPC·一人公司、产品设计、技术工程、数据智能、内容创作。
- 场景 3：内容创作 / 小微企业 / 数据分析（条目全失效的 投资分析·法律咨询·电商运营 整张删）。

按用户界定，`NP_EXPERTS`(8)、`catalog_experts`(13)、`experts`(0) 均未动。

### 验证

- `npx tsc --noEmit` 通过（`catalog.ts` 元组类型未破）。
- **陷阱 1 回归（关键）**：没有重启用户正在跑的 :8000，而是把裁剪后的库复制一份，用 `AGENTMATE_DB`
  env 覆盖（`config.py:81` 为隔离测试预留）指向副本，**连跑两次真 `db.init_db()`**（即 `main.py:102`
  的冷启动路径，含 `_seed_catalog`+`_seed_showcase`）→ 四个 kind 仍为 3/6/7/3，未被重种。
- **层间一致性**：写脚本从 `catalog.ts` 正则抽取四段与种子 JSON 逐字比对 → 四项全 OK
  （即「后端断连时的兜底」与「正常状态」是同一份）。
- **API**：`GET /api/catalog` → EXP_SCENES=3 / EXP_GRID=7 / EXP_TEAMS=3 / EXP_CATS=6，NP_EXPERTS 仍 8。
- **UI（Playwright 实测）**：DOM 断言精选场景 3 张、专家 7 张、专家团 3 张、分类 6 个，与名单逐一对上；
  「专家 × 专家团」× 6 分类共 12 组合全点一遍（注意 React 异步渲染 —— 同步 click 循环会读到上一帧的陈旧计数，
  须每次点击后让出一帧再断言）；**明暗双主题**各截图核对，暗色无翻转翻车。
- **边界**：专家团 × OPC·一人公司 / 内容创作 两组无卡 → 正常落到既有空态 `.hub-blank`「该分类下暂无专家团」
  （该空态在裁剪前即可达，如 行业顾问 × 专家团，非本次引入）。
- commit：本次提交 `chore(WB-176): 精简专家/专家团橱窗数据 …`（共享树并发，走私有 GIT_INDEX_FILE
  + commit-tree + update-ref CAS 构建，未触碰工作区与共享 INDEX）。运行库 `agentmate.db` 的对账
  不进仓库（`.gitignore` 已排除），属本机运行时数据。
