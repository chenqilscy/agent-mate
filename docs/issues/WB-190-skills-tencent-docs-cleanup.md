---
id: WB-190
title: 技能侧仍留着「腾讯文档」条目（橱窗/推荐/SkillHub 商店），与连接器侧的下架不一致
severity: P3
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/data/catalog.ts:123
  - src/data/catalog.ts:102
  - src/data/catalog.ts:338
created: 2026-07-17
---

## 问题

WB-177 / WB-189 已按用户诉求把 `腾讯文档` 从连接器橱窗（`CONNS`）与项目连接器选择器
（`NP_CONNS` 及模板 `NP_TPLS`）下架，但**技能侧**同名条目仍在，用户确认要一并清：

- `SK_GRID`（技能橱窗，`src/data/catalog.ts:123`）：`['📘','腾讯文档','腾讯文档在线云文档平台…']`
  —— 真会渲染（`ExpertsView.tsx:482`），且 **DB 供给**（17 行）。
- `SK_RECO`（`:102`）：`['📄','腾讯文档高考志愿填报助手',…]` —— DB 供给（4 行），
  但**无任何组件消费**（只在 `catalogStore` 的键列表里过一道）＝死代码，与并发会话
  WB-184 的判断一致。
- `SKILLHUB_GRID`（`:338`）：`['腾','#1E6FFF','腾讯文档 TENCENT DOCS',…,'131k',183,'办公效率']`
  —— 真会渲染（`ExpertsView.tsx:460`），但**不入库**（`db.py:34` `_SHOWCASE_SKIP`，DB 0 行），
  只有静态一层。

补充事实：`backend/agent/skills.py` / `skills_store.py` 里**没有**「腾讯文档」技能定义 ——
这张卡本就零后端能力（同 WB-179 记的「SK_GRID 17 个里 11 个后端零能力」），
删掉它反而更贴铁律#1，不会藏掉任何真能力。

## 触发场景

App → 专家·技能·连接器 → 「技能」tab：连接器侧已无腾讯文档，技能橱窗与 SkillHub
商店网格里却仍列着它 —— 同一产品在同一页面下架得不干净。

## 影响

P3：纯目录数据，不影响运行时；只是与用户刚下的「去掉腾讯文档」界定不一致。

## 建议修法

- `SK_GRID`：删「腾讯文档」（17→16）—— **三层同步**（`catalog.ts` / `catalog_showcase.json` /
  运行库 `catalog_showcase`），同 WB-177/189 的做法。
- `SK_RECO`：删「腾讯文档高考志愿填报助手」（4→3）—— 同样三层（DB 有 4 行）。
  它是死代码，清它只为数据一致；若并发会话的 WB-184 后续整块删掉 `SK_RECO`，本改动自然作废。
- `SKILLHUB_GRID`：删「腾讯文档 TENCENT DOCS」—— 只改 `catalog.ts` 与种子 JSON 里的同名键
  （该 kind 被 `_seed_showcase` 跳过、DB 无行，种子里那份是惰性的，同步只为不留矛盾数据）。

范围内只清「腾讯文档」（用户本次确认的就是它）。**`SKILLHUB_GRID` 里的 `ima-skills`（:339）未动** ——
它是 ima 的技能版，用户当初的下架名单里有「ima知识库」但那指的是连接器，是否连带下架需其确认。
`QQ邮箱`/`腾讯新闻` 等其它腾讯系条目不在名单内，不动。

并发注意：技能子系统正被并发会话重构（WB-181 `SKILLHUB_GRID` 假 downloads/stars、
WB-183 技能目录入库、WB-184 数据源收敛），本改动只删条目、不改结构，尽量减少撞车面。

## 验证

- `npx tsc --noEmit`。
- 层间一致性：从 `catalog.ts` 抽 `SK_GRID`/`SK_RECO` 与种子逐字比对；`SKILLHUB_GRID` 两层比对。
- 陷阱回归：库副本连跑两次 `db.init_db()`，`SK_GRID`/`SK_RECO` 不被重种（且 `SKILLHUB_GRID` 仍 0 行）。
- `GET /api/catalog`：`SK_GRID` 16 条且无腾讯文档；`SK_RECO` 3 条。
- UI：技能 tab 实测（明暗双主题）—— 橱窗与 SkillHub 网格均无腾讯文档，其余卡正常。

## 处理记录（2026-07-17）

- 改动（三层同步，逐字一致）：
  - `SK_GRID` 17→16（删「腾讯文档」）、`SK_RECO` 4→3（删「腾讯文档高考志愿填报助手」）——
    `catalog.ts` / `catalog_showcase.json` / 运行库三层；运行库按名对账（DELETE×2 + sort 重排）。
  - `SKILLHUB_GRID` 删「腾讯文档 TENCENT DOCS」—— 仅 `catalog.ts` + 种子 JSON（该 kind 被
    `_seed_showcase` 跳过，DB 实测 0 行）。
- 验证：
  - `npx tsc --noEmit` 通过。
  - 层间一致性：从 `catalog.ts` 真抽取 7 个 kind 与种子逐字比对全 OK
    （CONNS 8 / CONN_META 2 / NP_CONNS 10 / NP_TPLS 6 / SK_GRID 16 / SK_RECO 3 / SKILLHUB_GRID 37）。
  - 陷阱回归：库副本连跑两次真 `db.init_db()` → SK_GRID=16 / SK_RECO=3 不被重种，SKILLHUB_GRID 仍 0 行。
  - 真 API：`GET /api/catalog` → SK_GRID 16 无腾讯文档、SK_RECO 3 无腾讯文档；响应无 SKILLHUB_GRID 键（本就不入库）。
  - UI（独立 headless chromium + CDP，明暗双主题）：技能页三段实测 ——
    **「推荐」段（SK_GRID）16 张卡、腾讯文档已消失 ✓**。

## ⚠️ 达成度：只清掉了「我们自己的目录」那一半

实测发现「SkillHub」段（369 张卡）**仍显示「腾讯文档 TENCENT DOCS」**。根因不是本改动没落地，
而是该段数据根本不是本地目录：接了 Hub 时它用的是**上游 skillhub.cn 商店的镜像**
（`ExpertsView.tsx:424-427`；本机 `HUB_URL=:8100` 且 `catalog_downlink` 有 skill 369 行），
静态 `SKILLHUB_GRID` 只是**未接 Hub/离线时的兜底** —— 故本次对它的编辑在当前环境下不改变显示。

这属另一类问题（第三方商店镜像的「本站下架」能力缺口，且 `replace_all_downlink` 每次清空重建，
删镜像行必被下次同步覆盖），已另开 **WB-191** 记录，不夹带进本条。
本条按其原定范围（我们自己的技能目录数据）已完成。

- commit：见下方提交记录。
