---
id: WB-177
title: 连接器橱窗改版 —— 去掉 5 个连接器、新增 WeKnora 知识库连接器
severity: P3
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/data/catalog.ts:130
  - src/data/catalog.ts:161
  - backend/storage/catalog_showcase.json:49
  - backend/storage/catalog_showcase.json:111
created: 2026-07-16
---

## 问题

用户诉求：连接器橱窗（专家/技能/连接器 三 tab 的「连接器」）的商品卡要调整 ——
**去掉** `ima知识库`、`乐享知识库`、`腾讯文档`、`TAPD`、`企查查` 五张卡，
**新增** `WeKnora知识库` 连接器卡。

现状 `CONNS`（`src/data/catalog.ts:130`）共 12 张卡，其中三张知识库/文档类
（ima / 乐享 / 腾讯文档）与本项目自 WB-173 起改用的自托管 WeKnora 知识库路线相悖 ——
知识库能力已经真接了 WeKnora（`backend/agent/weknora.py` + `knowledge_retrieve` /
`knowledge_add` 两个真工具），橱窗里却没有它，反而摆着一排接不了的同类卡。

与 WB-176 同源：橱窗数据分三层，任何一层不同步都会「复活」或前后端不一致。

## 触发场景

App → 顶部「连接器」tab → 卡片网格：现出现 ima知识库 / 乐享知识库 / 腾讯文档 /
TAPD / 企查查，且无 WeKnora 知识库。

## 影响

P3：纯目录数据，不影响运行时；但橱窗是产品门面，摆着一排与当前知识库路线相悖、
且点了也接不上的卡，而真接了的 WeKnora 反而缺席。

## 建议修法

三层同步（逐字一致），只改 `CONNS` 与 `CONN_META` 两个 kind：

- `src/data/catalog.ts` —— 前端静态兜底（`catalogStore.ts` 仅在后端返回该键时才覆盖）。
- `backend/storage/catalog_showcase.json` —— 后端种子（`_seed_showcase` 按 kind 查重，
  某 kind 删空则下次启动整批重种）。
- `workbuddy.db` 的 `catalog_showcase` 运行库 —— 按种子对账：落选行 DELETE、
  新增行 INSERT、留存行 sort 重排 0..n-1（与 `_seed_showcase` 的 enumerate 语义对齐）；
  `CONN_META` 是 `is_scalar=1` 单行整存，UPDATE 该行。

WeKnora 卡给 `CONN_META` 详情（同金山文档那条的结构）：`status: 'tok'`、启用说明指向
`backend/.env` 的 `WEKNORA_API_KEY` 与 `docs/weknora-部署.md`，`tools` 清单**逐字镜像**
后端真工具（`knowledge_retrieve` / `knowledge_add`，见 `backend/agent/tools.py:373,479`），
不编造能力（铁律#1）。

范围只限 `CONNS` / `CONN_META`；`NP_CONNS`（新建项目的连接器选择器，另含 乐享知识库 /
腾讯文档 / TAPD）与引用了它们的 `NP_TPLS` 项目模板按用户界定**未动**，如需一并裁剪另开 issue。

## 验证

- `npx tsc --noEmit` 通过。
- 陷阱回归：用 `WORKBUDDY_DB` 指向库副本连跑两次真 `db.init_db()`，`CONNS` 仍为 8 条、
  不被重种；不重启用户正在跑的 :8000。
- 层间一致性：从 `catalog.ts` 抽取 `CONNS`/`CONN_META` 与种子 JSON 逐字比对。
- API：`GET /api/catalog` 返回的 `CONNS` = 8 条且含 WeKnora知识库、不含被删 5 条。
- UI：浏览器实测明暗双主题，连接器 tab 卡片网格断言 8 张卡、WeKnora 卡可点开详情弹窗。

## 处理记录（2026-07-16）

- 改动（三层，逐字一致）：
  - `src/data/catalog.ts` —— `CONNS` 12→8（删 ima知识库/乐享知识库/腾讯文档/TAPD/企查查，
    在原 ima 的位置加 `📚 WeKnora知识库`）；`CONN_META` 加 `WeKnora知识库` 一条
    （`status:'tok'`、非 oauth，`tools` 逐字镜像 `backend/agent/tools.py` 的
    `knowledge_retrieve`/`knowledge_add`，不编造能力）。
  - `backend/storage/catalog_showcase.json` —— 同上两个 kind 定点同步（其余键零改动，不重排版）。
  - `backend/workbuddy.db` 的 `catalog_showcase` —— 脚本按名字对账（保留留存行 id）：
    INSERT WeKnora×1、DELETE×5、留存行 sort 重排 0..7、`CONN_META` scalar 行 UPDATE。
- 范围外（按用户界定未动）：`NP_CONNS`（新建项目连接器选择器）与 `NP_TPLS` 项目模板里仍有
  乐享知识库/腾讯文档/TAPD；Hub 的 `CONN_DEFS` 走 `NP_CONNS` 分类，与本次 `CONNS` 无关。
- 验证：
  - `npx tsc --noEmit` 通过。
  - 层间一致性：脚本用括号配平从 `catalog.ts` 真抽取 `CONNS`/`CONN_META`，与种子 JSON
    `JSON.stringify` 逐字比对 —— 两 kind 全一致（8 条 / 2 键）。
  - 陷阱回归：`sqlite3.backup` 取运行库快照，`WORKBUDDY_DB` 指向副本连跑两次真
    `db.init_db()`（含 `_seed_showcase`）→ 仍 8 条、不被重种；未重启用户正在跑的 :8000。
  - 真 API：`GET /api/catalog` → `CONNS` 8 条、无被删 5 条、含 WeKnora；
    `CONN_META.WeKnora知识库.tools = [knowledge_retrieve, knowledge_add]`、`status=tok`（无需重启即生效）。
  - UI：MCP 浏览器被并发会话占用 → 用独立 headless chromium + CDP 实测真页面：
    侧栏→连接器 tab，明暗双主题均 8 张卡且名单一致；WeKnora 卡徽标「需连接」，
    卡底色/描述色明 `#fff`/`rgb(91,97,105)`、暗 `rgb(34,39,45)`/`rgb(166,173,182)`（无白底白字）；
    详情弹窗渲染正常：能力介绍/启用方式/「能力清单 · 2 项工具」展开为两个真工具/两条试用问法/
    页脚「添加到本会话·去试试」（非 oauth 路径首次被覆盖到）。
- commit：未提交（用户未要求）。
