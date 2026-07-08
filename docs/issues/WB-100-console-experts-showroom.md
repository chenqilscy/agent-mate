---
id: WB-100
title: BuddyWebMgr 专家/专家团升级为 App 同款浏览橱窗（替裸 CRUD）
severity: P2
area: frontend
status: fixed
origin: 用户诉求 2026-07-09（把 App 的专家/专家团功能复制到控制台）
files:
  - hub/web/console.html:309
  - src/views/ExpertsView.tsx:62
created: 2026-07-09
---

## 问题

BuddyWebMgr 控制台（`hub/web/console.html`）「目录运营中心」的 **专家 / 专家团** 两个 tab 目前只是
**裸管理表单 + 纯文本列表**（新增/编辑/停用/删除 catalog_items）。而 WorkBuddy App 的
`src/views/ExpertsView.tsx` 有一套**精美浏览橱窗**：精选场景卡（EXP_SCENES）+ 专家/专家团子标签 +
分类筛选（EXP_CATS）+ 富卡片（EXP_GRID/EXP_TEAMS）+ 详情弹窗（能力介绍/擅长领域/团队成员/试试这样问我）。

两端读的是**同一份 Hub 目录数据**（`EXP_GRID` / `EXP_TEAMS` / `EXP_CATS` / `EXP_SCENES`，
控制台 `catalogView` 已经在用这些类别），差的纯是控制台侧的浏览 UI/体验。

用户要求（2026-07-09）：把 App 的专家/专家团功能**直接复制**进 BuddyWebMgr。经确认取
**精美浏览橱窗**形态（见「建议修法」）。

## 触发场景

登录 BuddyWebMgr（平台管理员）→ 目录运营中心 → 专家 / 专家团：只有表单和一行行文字列表，
与 App 里图文并茂的橱窗差距明显。

## 影响

P2：控制台是团队运营目录的入口，专家/专家团是最重的两类；浏览体验与 App 脱节，管理员看不到
「客户端最终长什么样」，择机对齐即可。

## 建议修法

在 `hub/web/console.html` 里把 `expertsCat` / `teamsCat` 两个裸 CRUD 视图，合并升级为一套
**App 同款橱窗**（沿用控制台既有 dark token：`--panel/--line/--brand/--dim/--ink/--chip`，
不引第三方，纯 vanilla + 模板字符串，风格对齐 App `src/styles/app.css` 的
`.scene-card/.ecard/.ec-*/.subtabs/.cats/.np-*`）：

- 顶部 **精选场景**（EXP_SCENES 只读场景卡；点击切到「专家团」子标签，同 App）。
- **专家 | 专家团** 子标签 + 右侧「＋ 新增」。
- **分类筛选**（EXP_CATS chips）。
- **富卡片网格**（EXP_GRID/EXP_TEAMS，取 `?all=true` 含停用项、停用卡置灰+「停用」标）。
- 卡片点击 → **详情弹窗**（能力介绍/擅长领域/团队成员/试试这样问我）；因控制台无对话，
  App 的「召唤」改为**纯预览**，弹窗底部放**管理动作**：编辑 / 停用·启用 / 删除。
- **新增/编辑** 复用现有表单字段，装进编辑弹窗（保住全部 CRUD 能力，不丢功能）。
- 合并后目录 tab 从 `[专家][专家团][连接器][技能][SkillHub][高级JSON]` 变为
  `[专家·专家团][连接器][技能][SkillHub][高级JSON]`（专家团成为内部子标签）。

数据全部来自现有 `/api/catalog/*` 端点，无需改后端。

## 验证

- 隔离 Hub :8100（hub-test.db，alice=平台管理员）起站，登录进目录运营中心 → 专家·专家团：
  - 精选场景卡渲染；专家/专家团子标签切换；分类 chips 过滤生效。
  - 富卡片图文正确（图标/名称/副标题/简介/标签）；停用项置灰可辨。
  - 点卡片开详情弹窗，专家团显示成员与示例问；底部编辑/停用/删除可用。
  - 新增一个专家 → 列表出现；编辑改名 → 生效；删除 → 消失（真调 catalog 端点）。
- 控制台横向不溢出（延续 WB-099 的 grid minmax(0,1fr) 约束）。
- 控制台是独立 dark-only 皮，无需明暗双主题；但需确认深底配色无「深底深字」。

## 处理记录（2026-07-09）

- 改动（仅 `hub/web/console.html`，纯 vanilla + 模板字符串，零后端改）：
  - 合并 `expertsCat` + `teamsCat` 两个裸 CRUD → 一套 **App 同款橱窗** `expertsCat`：精选场景卡（EXP_SCENES）
    + 专家/专家团子标签（EXPSUB）+ 分类 chips（EXP_CATS，自动补「全部」）+ 富卡片（EXP_GRID/EXP_TEAMS，
    `?all=true` 含停用项、停用置灰 `.off`）。
  - 卡片点击 → 详情弹窗（`expExpertDetail`/`expTeamDetail`）：能力介绍/擅长领域/团队成员(⭐主理人)/试试这样问我；
    **无「召唤」（纯预览）**，底部管理动作 编辑 / 停用·启用 / 删除。
  - 新增/编辑复用表单装进弹窗（`expExpertEdit`/`expTeamEdit`，`exe-`/`tme-` 前缀 + `ov.querySelector` 作用域，
    避免 id 撞车）；专家团补了可选 `badge` 字段。轻量弹窗骨架 `expModal`/`expClose`（遮罩/×/Esc 关）。
  - 目录 tab：`[专家][专家团]` 合并为 `[专家 · 专家团]`（专家团成为内部子标签）；派发表移除 `teams:teamsCat`。
  - 新增 CSS（复用 App `.scene-card/.ecard/.ec-*/.subtabs/.cats/.np-*/.pkc-*`，**全部改套控制台既有 dark token**
    `--panel/--line/--brand/--dim/--ink/--chip/--panel2`，无浅色写死、无深底深字）。
- 验证（隔离 Hub :8102 × scratchpad 独立 DB，alice=平台管理员，播种 15 分类/4 场景/9 专家/3 专家团）：
  - `node new Function` 语法检查内联 JS 通过（729 行）。
  - **DOM-shim 谐振器**跑「真·抽取的渲染函数」打实时 API：26 项断言全过——精选场景/子标签/分类 chips/富卡片名与标签/
    详情弹窗（能力介绍·擅长领域·团队成员·主理人·示例问·无召唤·管理动作齐）/无 `undefined` 泄漏。
  - **端到端 CRUD**（真调 catalog 端点）：新增 → 列表出现 → 改名 PATCH 生效 → 停用 enabled=false → 删除消失，全过。
  - 横向不溢出（沿用 WB-099 的 `card-grid g4 → minmax(0,1fr)` + 1080px 降 2 列）。
  - **浏览器内视觉走查（CDP 自截图）**：共享 Playwright MCP 浏览器一度被并发会话（WB-101）独占，遂启**独立 headless Edge**
    （独立 user-data-dir + `--remote-debugging-port=9333 --remote-allow-origins=*`），用 Node 内置 WebSocket 走 CDP 自截图。
    5 张实拍确认：精选场景卡 + 专家/专家团子标签 + 分类 chips + 富卡片；专家详情弹窗（能力介绍/擅长领域/编辑·停用·删除、
    **无召唤**）；子标签切专家团；专家团详情（团队成员·⭐主理人 + 试试这样问我）；「技术工程」分类过滤只剩「高级开发工程师」。
    计算样式：卡片 `--panel` 深底 + `--dim` 浅字、激活 chip 绿底白字——**无深底深字**。
- **诚实边界**：并发会话同期在同一文件做 WB-101（连接器橱窗，`cg-*` 前缀），本次改动与其无 class/函数交叠、合并后语法通过；
  共享文件**未 `git add`/提交**（避免与 WB-101 混提；留给用户按 hunk 暂存或待 WB-101 落定后同提）。
