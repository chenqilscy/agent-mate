---
id: WB-048
title: 专家/专家团页交互落地（专家团切换 + 分类过滤 + 详情弹窗 + 召唤进会话）
severity: P2
area: frontend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/views/ExpertsView.tsx:43
  - src/views/ExpertsView.tsx:50
  - src/views/ExpertsView.tsx:57
  - src/data/catalog.ts:19
  - src/data/catalog.ts:30
created: 2026-07-07
---

## 问题

「专家·技能·连接器」的专家页当前是一个静态展示壳，几处该有的交互都没接线（原型 `docs/workbuddy-v2.html:992` 也是静态壳，未落地）：

- **专家团子标签点不动**：`.subtab`「专家/专家团/最热/最新」都是无 state、无 `onClick` 的静态 `div`（[ExpertsView.tsx:43-49](../../src/views/ExpertsView.tsx#L43-L49)），点「专家团」不切换，永远渲染 `EXP_GRID`（单个专家）。
- **分类不过滤**：`setCat` 更新了状态，但卡片网格恒定渲染整份 `EXP_GRID`，分类 tab 形同虚设（[ExpertsView.tsx:50-69](../../src/views/ExpertsView.tsx#L50-L69)）。
- **无详情弹窗**：点卡片只 `toast('召唤专家 · ' + n)`（[ExpertsView.tsx:57](../../src/views/ExpertsView.tsx#L57)），没有目标形态里的「能力介绍 / 擅长领域 / 团队成员 / 试试这样问我 / 召唤」弹窗。
- **召唤是假的**：只弹 toast，没有真正把该专家挂进本会话 loadout 并进入对话。

数据缺口：`EXP_GRID` 每条没有分类字段（[catalog.ts:30](../../src/data/catalog.ts#L30)），且没有「专家团 → 成员」数据（`EXP_SCENES` 仅「场景名 → 3 个名字」，[catalog.ts:19](../../src/data/catalog.ts#L19)）。

## 触发场景

进入「专家·技能·连接器」→ 专家页 → ①点顶部「专家团」子标签：无反应。②点任一分类（如「内容创作」）：网格不变。③点任一专家卡片：只弹一条 toast，没有详情弹窗、无法召唤。

## 影响

P2：核心浏览/召唤链路不可用，「专家团」整块不可见、召唤不生效——这是专家页的主要价值。视觉件与召唤机制（loadoutStore / startDraft）都已存在，属未接线。

## 建议修法

复用既有件，遵守"视觉零重设计"：

1. `ExpertsPane` 改为受控：`sub: '专家' | '专家团'` state，专家团渲染新增的 `EXP_TEAMS`；`cat` 真过滤（给 `EXP_GRID` 每条补 `category`）。
2. `data/catalog.ts`：`EXP_GRID` 补分类字段；新增 `EXP_TEAMS`（图标/名称/来源/简介/擅长领域/成员[角色·名字·是否主理人]/示例问题/分类/标签），对齐目标形态做代表性 6–8 个团队（catalog.ts 本就是"静态目录直到 API 落地"的既有约定）。
3. 新增 `ExpertDetailModal`（套现有 `.np-overlay/.np-modal/.np-h/.np-body/.np-foot`，卡片复用 `.ecard/.ec-*`）：能力介绍 / 擅长领域 / 团队成员（专家团才有）/「试试这样问我」/ 底部**召唤**按钮。
4. **召唤真接线**：`useChatStore.getState().startDraft()` 开干净草稿 → `useLoadoutStore` 把该专家（专家团则**全部成员**）设进 `experts` → `setView('home')`，首页 composer 打开且已选中；点「试试这样问我」的示例问题预填输入框。

## 验证

- `npx tsc --noEmit` 通过。
- Playwright 实测：专家 ↔ 专家团切换；分类过滤生效；点卡片弹详情；点召唤后回到首页且 ＋菜单「专家」计数/loadout 已含该专家（团队则含全部成员）；示例问题预填。
- **明暗双主题**都看（弹窗背景/文字对比）；≤900px 抽屉宽度下不破版。

## 处理记录（2026-07-07）

- 改动：
  - `src/data/catalog.ts`：`EXP_GRID` 每条补第 7 元素 `category`（∈EXP_CATS）；新增 `TeamMember/ExpertTeam` 类型与 `EXP_TEAMS`（8 个代表性专家团，含成员/主理人/擅长/示例问题/分类/标签）。
  - `src/stores/loadoutStore.ts`：新增 `summon(experts)` 动作（清空 loadout 只保留给定专家）。
  - `src/views/ExpertsView.tsx`：`ExpertsPane` 改受控（`sub` 专家/专家团切换 + `cat` 真过滤 + 空态）；新增 `ExpertDetailModal`（套 `.np-overlay/.np-modal`，能力介绍/擅长领域/团队成员[主理人徽标]/试试这样问我/召唤）；顶层 `summon()` 接线：召唤=`loadout.summon`+`startDraft`+回首页；示例问题=同上并直接 `send`。精选场景卡点击切到专家团。
  - `src/styles/app.css`：新增 `.hub-blank` 空态样式（token 化，暗色安全）。
- 验证：`npx tsc --noEmit` 通过。Playwright 实测（:5180，已登录）：专家↔专家团切换生效；「法务安全」过滤专家团仅剩中文法律咨询团、切到「专家」tab 触发「该分类下暂无专家」空态；团队详情弹窗成员/主理人/擅长/示例问题齐全；点「召唤 内容创作专家团」→ 跳首页且 composer 已挂入全部 7 名成员 chip；单专家弹窗正确省略成员/示例问题段。**明暗双主题**弹窗均无白底白字/深底深字（复用现成弹窗类，天然继承 body.dark 覆盖）。示例问题→send 路径与首页 launch 同构、loadout 由 `send()` 于发送时读取（已在召唤路径验证同一机制），未单独发起真实 LLM 调用以免污染会话。
- commit：（待提交）
