---
id: WB-181
title: 技能页假交互清理 —— 推荐段＋号/安装套件/排序/＋添加技能 全是 toast 桩（铁律#1）
severity: P1
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:45
  - src/views/ExpertsView.tsx:505
  - src/views/ExpertsView.tsx:440
  - src/views/ExpertsView.tsx:745
  - src/views/ExpertsView.tsx:91
  - src/views/ExpertsView.tsx:723
created: 2026-07-16
---

## 问题

技能页（`ExpertsView.tsx`）上多个按钮**只弹 toast，无任何副作用**，UI 对用户撒谎。逐条已核实：

1. **`ExpertsView.tsx:45-60` `AddBtn`** —— 「推荐」段每张卡右上的 ＋ 号。
   `onClick={() => { setOn(v => !v); toast(!on ? '已添加' : '已移除') }}`
   —— 只翻转组件内 `useState`，**不进 loadout、不安装、不落任何地方**，刷新即复原。
   对比：连接器卡的 `ConnAddBtn`（L579）是真的，受控于 `loadoutStore.connectors`。
2. **`ExpertsView.tsx:505` 「安装套件」** —— `onClick={() => toast('安装套件 · ' + name)}`，
   **不装任何技能**（套件本身的虚构问题见 WB-182）。
3. **`ExpertsView.tsx:440` 排序** —— `onClick={() => toast('排序 · 综合评分')}`，不排序。
4. **`ExpertsView.tsx:745` 「＋ 添加技能」** —— `onClick={() => toast('添加技能')}`，右上主按钮无功能。
5. **`ExpertsView.tsx:91-92`** 专家段「最热 / 最新」两个 subtab —— 无 onClick、无状态，纯装饰。
6. **`ExpertsView.tsx:723` `onAct`** —— `skills`/`connectors` 分支只 toast 标签名。

另有**写死的假统计**：`SKILLHUB_GRID`（`catalog.ts:323-362`）39 条卡的 `downloads`/`stars`
全部手写（`'174k', 109` / `'131k', 183` / …），在离线/无 CLI 时**照常渲染给用户看**。
WB-071 已把它降级为第 3 层兜底，但未删除。★/⬇ 也**只是展示数字，无 onClick，不是收藏功能**。

## 触发场景

技能页 → 「推荐」子 tab → 点任意卡的 ＋ → toast「已添加」→ 回首页看 loadout：**什么都没有**。
刷新技能页 → ＋ 号复原。

## 影响

P1，违反铁律#1。这批是本项目反复出现的"占位桩"类问题（同 WB-024/WB-028/WB-137/WB-085），
按既有处理惯例：**要么接真实现，要么诚实占位**，不能假装成功。

## 建议修法

逐条二选一（接真 / 诚实占位），建议：

1. `AddBtn`（推荐段）：接 `loadoutStore.toggle('skill', slug)`，与 SkillHub 段的 `InstallBtn` 语义统一；
   若该段在 WB-184 收敛后消失，则随之删除。
2. 「安装套件」：依赖 WB-182 的结论 —— 真做则接批量安装端点，删则连同 `KitView` 一并移除。
3. 排序：接 `/api/skills/rankings?type=` 已支持的枚举（featured/hot/newest/recommended/trending），
   后端已就绪（`skills.py:47`），前端只是没接；接不了的排序项不显示。
4. 「＋ 添加技能」：接「从本地目录导入 / 打开 SkillHub 搜索」之一，或删除。
5. 专家段「最热/最新」：接排序或删（注：专家段测试按用户要求可跳过，但假按钮仍应清理）。
6. `SKILLHUB_GRID` 静态假统计：WB-071 已提供真实 rankings 兜底，**删除这 39 条**及其写死的
   downloads/stars（与 WB-184 的数据源收敛一并做）。

## 验证

- `npx tsc --noEmit` 过。
- grep `ExpertsView.tsx` 确认无「只 toast 不做事」的 onClick 残留。
- Playwright/CDP 逐个点击：每个按钮要么产生可观测的真实状态变化（loadout / 安装 / 排序结果变化），
  要么明确显示「即将上线」（参考 WB-028 的诚实占位范式）。
- 明暗双主题都看（`.add-btn` 有暗色历史坑，见 WB-008）。

## 处理记录（2026-07-17）

技能页的假交互**清完**（6 项里 3 项修、1 项归 WB-182、2 项非技能页范围）。

### 先摸清「推荐」段那 16 张卡到底是什么

修 `AddBtn` 前必须知道 ＋ 该做什么。实测（打真后端 + 上游）：

| 身份 | 张数 | 例 |
|---|---|---|
| **内置技能**（`SKILLS` dict，带真工具，装不了——本来就自带） | **6** | Web Access / MarkItDown / Excel 文件处理 / 技能创建指南 / Word 文档生成 / 股票综合分析器 |
| **可装**（名字精确解析到真 slug） | **3** | 腾讯自选股-金融数据查询→`westock-data` / skill-creator / 腾讯新闻→`tencent-news` |
| **上游根本不存在** | **7** | NeoData金融搜索服务 / A股全栈数据 / QQ音乐助手 / IMAP/SMTP邮件 / fbs-bookwriter / QQ邮箱 / 创业可以学 |

那 7 张不是「名字对不上」——逐个搜上游确认过：搜任何一个中文名都只回
`self-improving-agent`/`find-skills`/`summarize` 这几个通用结果，即**上游没有对应技能**，
是设计阶段编的商品卡。（「QQ邮箱」倒有相关的「QQ邮箱发票下载器」，但没有叫「QQ邮箱」的。）

**一个 ＋ 不可能同时服务三种语义** —— 这本身是数据问题，归 WB-184/WB-183。

### ✅ 1. `AddBtn` → `RecoBtn`：按真实身份分派

- **内置 / 已装且未停用** → 挂载进会话并跳 composer；
- **其余** → 复用既有 `InstallBtn`（真安装，装不到诚实报错）。

**为什么是「挂载+跳转」而不是留在原地 toggle**（第一版就是 toggle，实测发现不行）：
loadout 是**会话级**的，`chatStore.ts:70` 的 `openSession` 和 `Sidebar.tsx:171` 的 `newTask`
都会 `reset()` 它 —— 这是 WB-003 的**正确行为**。所以原地 toggle 会得到
「状态是真的、但用户一导航去用就没了」= 真状态、假用处。
本 app 既有的正确出路是 **summon 系**（设 loadout → `startDraft`（不 reset）→ `setView`）：
专家「召唤」(`ExpertsView.tsx:30`)、技能详情「去试试」(`SkillDetail.tsx:60`) 都走这条，
这里保持一致，零新机制。

### ✅ 2. 「综合评分」排序控件 → 移除

`onClick={() => toast('排序 · 综合评分')}`，不排任何序。**没有接真排序**，因为：后端
`/skills/rankings` 的 `featured|hot|newest|recommended|trending` 早已就绪，但这一段的主数据源
是 **Hub 镜像**（不经 rankings），接上去只会得到「切了排序但只有部分数据源生效」的**新谎**。
真排序要等 **WB-184** 把三层数据源收敛掉。移除 > 留一个说谎的控件。

### ✅ 3. 「＋ 添加技能」→ 真聚焦搜索框

`onClick={() => toast('添加技能')}` → 回到浏览态 + `searchRef.current?.focus()`。
输入即触发既有 `SkillSearchResults` 的真实搜索/安装链路。

### ✅ 4. 「安装套件」→ 随 WB-182 整体删除（同日）

本条初次处理时它还是 `toast('安装套件 · ' + name)`，等 WB-182 的产品决策。
当日 WB-182 取「删掉」，整个「套件」段（含这个按钮）已移除 —— 技能页假按钮**清零**。

### 不在本条范围（如实记录）

- **第 5 项 专家段「最热/最新」**：非技能页，且用户已明确让专家功能靠后。
- **第 6 项 `onAct` 的 connectors 分支**（`toast('自定义连接器')`）：非技能页；
  「自定义连接器」是一整个功能，不是清理，应按 WB-028 的诚实占位范式另议。
- **第 7 项 `SKILLHUB_GRID` 写死的 downloads/stars**：属静态假数据，归 **WB-184**
  （该条本就要删这批静态兜底）。注：并发会话的 WB-190 已把「腾讯文档」从三层同步删掉，
  SK_GRID 17→16、SKILLHUB_GRID 38→37。

### 顺手发现，已另开 issue（不夹带）

- **WB-194**：连接器卡的 ＋ 是真状态但假用处 —— 同样被 `openSession`/`newTask` 的 reset 清掉，
  且与本条修完后的技能段行为不一致。
- **WB-195**：「推荐」段分类 chip 点了不过滤 —— 根因是 `SK_GRID` 的 `[icon,name,desc]`
  **没有分类字段**，当前数据下过滤无从实现；依赖 WB-183 的 `catalog_skills.category`。

### 验证

- `npx tsc --noEmit`（仓库根）过。
- **CDP 自驱实测 8 项全过**（Playwright MCP 浏览器仍被并发会话的进程占着，走独立 headless Edge；
  我的 vite 在 :5174）：
  - 推荐段 16 张卡的 `aria-label` 逐一核对：**6 张「挂载到本会话」/ 10 张「安装」**，分派正确；
  - 点内置卡「Excel 文件处理」的 ＋ → **跳到 home 且 Composer 真出现 chip `["Excel 文件处理"]`**
    （旧 `AddBtn` 什么都不做）；
  - 点虚构卡「QQ音乐助手」的 ＋ → toast **「SkillHub 未找到「QQ音乐助手」」**
    —— 诚实报错，不再假装「已添加」（WB-187 的精确匹配在这里兑现）；
  - `.sk-sort` 元素数 = 0（说谎的排序控件已消失）；
  - 「＋ 添加技能」→ `document.activeElement` 是 placeholder 含「搜索技能」的 input。
- 测试自身两次修正：① loadout chip 渲染在 Composer（对话页），技能页上没有，起初找错了地方；
  ② 起初经「新建任务」导航去看 chip —— 那正好触发 `newTask` 的 reset，把要验的状态清了。

### 状态

`fixed` —— 技能页假交互清零（套件项随 WB-182 的删除一并了结）。

- commit：未提交（待用户确认）。
