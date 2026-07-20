---
id: WB-182
title: 「套件」100% 虚构 —— 前端 4 条静态卡、后端零代码、Hub 无源、DB 无表
severity: P2
area: fullstack
status: fixed
origin: 🏚 迁移遗留
files:
  - src/data/catalog.ts:365
  - src/views/ExpertsView.tsx:495
  - backend/storage/db.py:34
  - hub/skillhub_sync.py
  - docs/agentmate-hub-架构设计.md:116
created: 2026-07-16
---

## 问题

技能页「套件」子 tab 展示 4 个套件（腾讯云运维套件 · 8 个技能 / 内容创作套件 · 6 个 /
金融投研套件 · 5 个 / 安全防护套件 · 4 个），**整个概念在后端一行代码都没有**：

- `SKILLHUB_KITS`（[catalog.ts:365-370](../../src/data/catalog.ts)）是前端静态四元组，
  「N 个技能」的 N 是**手写的常量**（8/6/5/4），**没有任何技能列表与之关联**。
- grep `kit|bundle|套件` 覆盖 `backend/**/*.py` → **零命中**。
- Hub 侧同样无 kit 概念；`skillhub_sync.py` 只镜像 `skill` / `skill-category` 两类。
- `db.py:34` 的 `_SHOWCASE_SKIP` 把 `SKILLHUB_KITS` **明确排除出 seed** → 那 4 条永不入 App DB。
- 早期 Server 架构设计曾包含 `catalog_skills.kit_id` 字段，但**从未实现**。
- 「安装套件」按钮是 toast 桩（见 WB-181 第 2 条）。

即：这是一个**纯展示的虚构商品**，点击无效，数字杜撰。

## 触发场景

技能页 → 「套件」子 tab → 「腾讯云运维套件 · 8 个技能」→ 点「安装套件」→
toast「安装套件 · 腾讯云运维套件」→ **零个技能被安装**，也无法查看这 8 个技能是哪些。

## 影响

P2，违反铁律#1。不是 P1 的原因：它是一个自成一体的 tab，不像 WB-179/180 那样污染核心链路；
但它是本次审查里**唯一 100% 虚构（前端到后端到 DB 全无支撑）**的功能。

## 建议修法

二选一，需用户决策：

**A. 真做（范围含 Hub/Manager）**
- Hub 建 `catalog_items` 新 category（如 `SKILL_KITS`），`data` 含 `{name, icon, color, desc, slugs: []}`；
  复用 WB-082/083/101 的目录运营 CRUD 范式（console.html，注意并发用独立 class 前缀）。
- App 经 `catalog_downlink` 下发消费；「安装套件」= 对 `slugs[]` 逐个走已有
  `POST /api/skills/install`（前端并发 + 逐项进度，无需新后端端点）。
- 「N 个技能」由 `slugs.length` 真算，不再手写。

**B. 删掉**
- 移除 `SKILLHUB_KITS` + `KitView` + 「套件」子 tab；`catalog_showcase.json` 里的 4 条一并清理。

倾向 **A**：批量装机是 SkillHub 场景下有真实价值的能力，且后端安装端点已就绪，成本主要在 Hub 运营 UI。
若近期不做，则应选 B —— 现状（虚构商品 + 假按钮）是最坏的。

**注意复活陷阱**（见 WB-176 的教训）：三层数据源（前端静态兜底 / 后端种子 / 运行库）需同步改，
否则「删空即重种」或「兜底顶上来」。

## 验证

- **若 A**：Manager 建一个含 3 个真实 slug 的套件 → App 拉到 → 点「安装套件」→
  `~/.agentmate/skills/` 下真出现 3 个目录 → 「我安装的」+3 → ＋ 菜单能选到（配合 WB-180）；
  卡片上的「N 个技能」= 3 而非手写值。
- **若 B**：grep `SKILLHUB_KITS|KitView|套件` 在 `src/` 下为空；技能页无「套件」tab；
  `npx tsc --noEmit` 过。

## 处理记录（2026-07-17）

**取 B（删掉）**。用户三次未就 A/B 表态，最后一次明确「如果你没意见我就删」后回「继续」，据此执行。

理由：这是整次技能审查里**唯一 100% 虚构**的功能 —— 后端 `grep kit|bundle|套件` 零命中、
DB 无表、Hub 无源、`_SHOWCASE_SKIP` 让它永不入库、「N 个技能」是手写常量（8/6/5/4）且
**没有任何技能列表与之关联**、「安装套件」只 toast。留着就是留个假按钮（卡着 WB-181 收尾）。
真要做，等 WB-183 的 `catalog_skills`（slug 主键）落地后在 Hub 建 kit 表会自然得多 ——
`data` 存 `{name, icon, color, desc, slugs[]}`，「N 个技能」由 `slugs.length` 真算，安装 =
对 `slugs[]` 逐个走已有的 `POST /api/skills/install`（无需新后端端点）。该方案已留在
`catalog.ts` 原处的注释里，需要时照做即可。

### 删除面比预想大 —— 5 处，漏一处就留孤儿

| 层 | 内容 |
|---|---|
| 前端数据 | `src/data/catalog.ts` `SKILLHUB_KITS`（4 条） |
| 前端视图 | `src/views/ExpertsView.tsx`：import / `KitView` / seg 类型 `'kit'` / seg tab / 渲染分支 |
| 后端种子 | `backend/storage/catalog_showcase.json` 的 `SKILLHUB_KITS` 键（4 条） |
| 后端配置 | `backend/storage/db.py` `_SHOWCASE_SKIP` 摘掉 `"SKILLHUB_KITS"`（JSON 里已无该键，留着是死配置） |
| **Manager** | `hub/web/console.html`：`SG_KITS` / `sgKit()` / `sgKits()` / seg tab / 分发分支 / 5 条 `.sg-k*` CSS / 2 处宣称有套件的旧注释 |

**Manager 那层差点漏掉**：WB-102 当初把 App 技能页整页镜像到 console 时连套件一起搬了过来，
App 删了而 console 不删就会留一个点开空白的孤儿 tab。
另清了 `src/styles/app.css` 的 `.kc-count`（随 `KitView` 死掉）。

### 复活陷阱（WB-176 的教训）—— 实测两条都不成立

- **删空即重种**：查真库 `catalog_showcase` 里 KIT 相关行 = **0**
  —— 因为 `_SHOWCASE_SKIP` 从来就没让它入过库，不存在「JSON 删了但库里还有」。
- **兜底顶上来**：`showcase_all()` 返回的 22 个键里**无任何含 KIT 的**。

### 验证

- `npx tsc --noEmit`（仓库根）过；`py_compile db.py` 过；`catalog_showcase.json` 仍是合法 JSON
  （23 个顶层键，`SKILLHUB_KITS` 已不在）。
- **App 侧 CDP 实测 6 项全过**：技能页分段 tab = `["推荐","SkillHub"]`（「套件」已消失）；
  SkillHub 段仍渲染 **369 张真卡**、推荐段仍 16 张（没删出破洞）；
  全页 `安装套件` 按钮数 = **0**；无 JS 报错。
- **Manager 侧静态校验全过**（console.html 是单文件无构建管线，路由是 `/` 不是 `/console.html`）：
  8 个已删标识符（`SG_KITS`/`sgKits`/`sgKit`/`sg-kit`/`sg-kic`/`sg-kcount`/`data-seg="kit"`/
  `SG_SEG==='kit'`）**残留均为 0**（有残留即运行时 ReferenceError）；保留的
  `sgReco`/`sgSkillhub`/`sgFeatured`/`data-seg="reco"`/`data-seg="skillhub"` 均在；
  内联 script 花括号/圆括号配平（防删出语法错）。

- commit：未提交（待用户确认）。
