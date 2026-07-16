---
id: WB-189
title: 新建项目的连接器选择器/模板仍留着已下架的连接器（乐享知识库/腾讯文档/TAPD）
severity: P3
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - src/data/catalog.ts:274
  - src/data/catalog.ts:225
  - backend/storage/catalog_showcase.json
created: 2026-07-16
---

## 问题

WB-177 按用户诉求把**连接器橱窗**（`CONNS`）里的 ima知识库 / 乐享知识库 / 腾讯文档 / TAPD / 企查查
下架了，但同一批连接器在**新建项目的连接器选择器**（`NP_CONNS`，`src/data/catalog.ts:274`）里仍在：
`TAPD`(:280) / `乐享知识库`(:285) / `腾讯文档`(:286)。用户诉求是「不要这些连接器」，
橱窗没了、建项目时却还能选，是同一诉求下的不一致（WB-177 当时按其界定只动了 `CONNS`，明确留了此条）。

更糟的是 `NP_TPLS`（项目模板，`:225`）不只在 conn 列表里引用它们，**人格提示词正文里也写着**：
`src/data/catalog.ts:237` —— 「在 TAPD 中跟进需求流转与缺陷状态，重要变更同步到腾讯文档」。
这段会被真注入 system_prompt，等于指挥 agent 去用一个**后端根本没有**的连接器
（`catalog_connectors` 里只有 本地便签/时间助手/工作区检索/GitHub/Telegram 五个真的），
属铁律#1「不硬编码、不模拟」——不能让提示词承诺不存在的能力。

## 触发场景

新建项目 → 「添加连接器」选择器：仍列出 乐享知识库 / 腾讯文档 / TAPD。
选「产品需求全流程」模板建项目 → 该项目的 system_prompt 含「在 TAPD 中跟进…同步到腾讯文档」，
而这两个连接器既不在橱窗、后端也无实现 → agent 被指使去用不存在的东西。

## 影响

P3：纯目录/模板数据，不影响运行时；但与用户刚下的「去掉这些连接器」的界定相悖，
且模板提示词指向不存在的能力。

## 建议修法

三层同步（同 WB-177/176 的三层：`catalog.ts` / `catalog_showcase.json` / 运行库 `catalog_showcase`），
只动 `NP_CONNS` 与 `NP_TPLS` 两个 kind：

- `NP_CONNS`：删 `TAPD` / `乐享知识库` / `腾讯文档`（13 → 10）。
- `NP_TPLS`：把各模板 conn 列表里的这三个删掉；**并改写提示词里点名它们的句子**（:237），
  改为不点名具体产品的通用表述（模板仍成立，且不再承诺不存在的连接器）。
- **不往 `NP_CONNS` 加 WeKnora**：项目挂知识库走的是另一条真路径（`NewProjectModal` 的 `kb` 选择器
  读 `knowledgeStore` 的真库），WeKnora 不是 MCP 连接器，摆进连接器选择器点了也是空转。

范围外：`SK_GRID`/`SK_RECO`/`SKILLHUB_GRID` 里的「腾讯文档」是**技能**（skill）不是连接器
（`catalog.ts:123`/`:102`/`:341`），用户这次界定的是连接器，故不动。
Hub 下发：`catalog_downlink` 当前只有 `skill`/`skill-category` 两类，未覆盖 `NP_CONNS`，
故本地三层即权威（若日后 Hub 推同名分类会覆盖本地，见 `db.showcase_all`）。

## 验证

- `npx tsc --noEmit`。
- 层间一致性：从 `catalog.ts` 抽 `NP_CONNS`/`NP_TPLS` 与种子 JSON 逐字比对。
- 陷阱回归：库副本连跑两次 `db.init_db()`，两 kind 不被重种。
- `GET /api/catalog`：`NP_CONNS` 10 条且无被删三个；`NP_TPLS` 无引用被删连接器、提示词不再点名。
- UI：新建项目 → 连接器选择器实测（明暗双主题），确认三个已消失、其余可选。

## 处理记录（2026-07-16）

- 改动（三层同步，逐字一致）：
  - `src/data/catalog.ts` —— `NP_CONNS` 13→10（删 TAPD/乐享知识库/腾讯文档）；
    `NP_TPLS` 五个模板的 conn 列表清掉这三个（项目交付 → 只剩 企业微信、Bug 跟踪 → 只剩 CNB，
    另三个变空），**并改写「产品需求全流程」阶段三的提示词**：
    「在 TAPD 中跟进需求流转与缺陷状态，重要变更同步到腾讯文档」→
    「跟进需求流转与缺陷状态，重要变更同步给相关方并留档」（不再指挥 agent 用不存在的连接器）。
  - `backend/storage/catalog_showcase.json` —— 两个 kind 定点同步（其余键零改动）。
  - 运行库 `catalog_showcase` —— 脚本按名字对账（NP_CONNS 用 `el[1]`、NP_TPLS 用 `el[0]` 作身份）：
    DELETE×3、留存行 sort 重排 0..9、NP_TPLS 五行 data UPDATE。
- 未加 WeKnora 进 `NP_CONNS`（理由见上：项目挂知识库走 `kb` 选择器的真路径，连接器位置放它是空转）。
- 验证：
  - `npx tsc --noEmit` 通过。
  - 层间一致性：脚本从 `catalog.ts` 真抽取四个 kind 与种子逐字比对，全 OK
    （CONNS 8 / CONN_META 2 / NP_CONNS 10 / NP_TPLS 6）；并断言模板 conn 列表与**提示词正文**
    均不再出现被删连接器。
  - 陷阱回归：库副本连跑两次真 `db.init_db()` → CONNS=8 / NP_CONNS=10 / NP_TPLS=6，未被重种。
  - 真 API：`GET /api/catalog` → `NP_CONNS` 10 条无被删三个；`NP_TPLS` conn 引用
    `{产品需求全流程:[], 市场调研:[], 团队知识库:[], 项目交付:[企业微信], Bug跟踪:[CNB], 自定义:[]}`；
    提示词无点名。**无需重启后端**（showcase_all 每请求读库）。
  - UI：独立 headless chromium + CDP 实测（MCP 浏览器仍被并发会话占用）：
    项目 → 新建项目 → 连接器（可选）「＋ 添加」→ 弹窗「添加连接器」列 10 项
    （本地便签/时间助手/工作区检索 带「内置」徽标，GitHub/Telegram 带「需配置」），
    三个已删连接器均不在；明暗双主题弹窗底色/文字色正常（浅 `#fff`/`rgb(31,35,41)`，
    暗 `rgb(31,36,42)`/`rgb(231,234,238)`）。
  - 过程校验：曾想用脚本整文件重写种子 JSON，脚本先做「JS 序列化能否逐字复现现有文件」自证 →
    **不一致（与 Python `json.dump(indent=1)` 有出入）即中止**，改走定点编辑，避免搅乱其余 key。
- 范围外（未动，如需另开 issue）：`SK_GRID`/`SK_RECO`/`SKILLHUB_GRID` 里的「腾讯文档」是**技能**不是连接器。
- commit：未提交（用户未要求）。
