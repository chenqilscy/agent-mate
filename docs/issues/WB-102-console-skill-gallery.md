---
id: WB-102
title: BuddyWebMgr 技能目录只有 CRUD 管理，缺主应用那样的「浏览橱窗」（整页技能）
severity: P2
area: frontend
origin: 用户诉求 2026-07-09（把 App 的技能功能复制到控制台）
status: fixed
files:
  - hub/web/console.html:474
  - src/views/ExpertsView.tsx:214
created: 2026-07-09
---

## 问题

BuddyWebMgr 控制台（`hub/web/console.html`）「目录运营中心」的 **技能** tab 目前只是
**裸管理表单 + 纯文本列表**（`skillsCat`，SK_GRID 三元组 [icon,name,desc] 的增/改/停/删）。
而 AgentMate App 的技能页（`src/views/ExpertsView.tsx:214` 起，`SkillsPane`）是一整套
**精美浏览橱窗**：

- 顶部 **精选技能**（SKILLHUB_FEATURED）大卡 + 「换一换」轮换；
- **推荐 | SkillHub | 套件** 三段切换（推荐=SK_GRID 卡、SkillHub=真实镜像 369 技能网格、套件=技能包）；
- **分类 chips**（skill-category 场景）+ skillhub.cn 链接 + 排序；
- **富卡片**（图标/名称/简介/★收藏/⬇下载）；
- **技能详情**；顶栏 **实时搜索**（走 CLI 代理）。

两端读的是**同一份 Hub 目录数据**（`SKILLHUB_FEATURED` / `SK_GRID` / `skill` / `skill-category`，
控制台 `catalogView`/`skillhubCat` 已在用这些类别），差的纯是控制台侧的浏览 UI/体验。

用户要求（2026-07-09）：把 App 的技能功能**直接复制**进 BuddyWebMgr，取「整页技能」形态。
本条是 WB-100（专家橱窗）/ WB-101（连接器橱窗）系列的**技能版**。

## 触发场景

登录 BuddyWebMgr（平台管理员）→ 目录运营中心 → 技能：只有「新增技能」表单和一行行文字列表，
与 App 里图文并茂的技能市场差距明显。

## 影响

P2：控制台是团队运营目录的入口，技能是最重的一类；浏览体验与 App 脱节，管理员看不到
「客户端技能市场最终长什么样」。无功能性缺陷。

## 建议修法

仿 WB-101，在 `skillsCat` 的「技能」tab 顶部加子切换：**浏览橱窗 | 目录管理**
（模块级状态 `SKILLSUB`，仿 `CATVIEW`/`CONNSUB`）。新增 CSS/DOM 用 `sg-` 前缀，避免与并发
会话（WB-086/100 也在改 console.html）撞类名。视觉沿用 console 自有暗色 token
（`--panel/--panel2/--line/--brand/--dim/--ink/--chip`），布局对齐 App `src/styles/app.css`
的 `.fcard/.hcard/.hc-*/.fc-*/.sk-seg/.cats/.card-grid`。

- **浏览橱窗**（新增，默认）：
  - **精选技能**（读 `GET /catalog/SKILLHUB_FEATURED`，空则静态兜底）大卡网格 + 「换一换」轮换。
  - **推荐 | SkillHub | 套件** 三段：
    - 推荐 = `GET /catalog/SK_GRID`（三元组卡）；
    - SkillHub = `GET /catalog/skill`（镜像富卡）+ `GET /catalog/skill-category`（分类 chips）+
      skillhub.cn 链接；空则静态兜底 SKILLHUB_GRID/CATS；
    - 套件 = 静态 SKILLHUB_KITS（Hub 无套件源，双列卡片）。
  - **搜索框**：非空 → 走 `GET /catalog/skills/search?q=`（CLI 代理），全屏结果网格。
  - 卡片点击 → **只读详情浮层**（图标/名称/分类·来源徽章/★·⬇/完整简介/「在 skillhub.cn 查看」链接）。
- **目录管理**（保留现状）：即现有 `skillsCat` 的 SK_GRID 表单 + 列表 CRUD。

**不搬**（Hub 控制台无本地技能后端 —— install/我安装的/SKILL.md 详情都依赖本地 App
`/api/skills/*`）：真安装、「我安装的」、SKILL.md 源码预览。App 卡片右上的「＋安装」在控制台
无意义，改为整卡点击开只读详情。诚实不做假动作（铁律#1）。

数据全部来自现有 `/api/catalog/*` 端点，无需改后端。

## 验证

- 隔离 Hub :8100（hub-test.db，alice=平台管理员）起站，登录进目录运营中心 → 技能：
  - 默认见「浏览橱窗」：精选技能大卡 + 换一换轮换；推荐/SkillHub/套件三段切换。
  - SkillHub 段：分类 chips 过滤生效；富卡图文正确（图标/名称/简介/★/⬇）；skillhub.cn 链接可点。
  - 搜索框输入 → 走 CLI 代理出结果网格（CLI 不可用时诚实空态）。
  - 点卡片出只读详情浮层（元数据 + skillhub.cn 链接）。
  - 子切换到「目录管理」见原 SK_GRID CRUD；来回切换不丢；新增/编辑/停用/删除照常。
- 控制台横向不溢出（延续 WB-099 的 grid minmax(0,1fr) 约束）。
- 控制台是独立 dark-only 皮，无需明暗双主题；但需确认深底配色无「深底深字」。

## 处理记录

2026-07-09：实现。仿 WB-101 在 `skillsCat` 加子切换「浏览橱窗 | 目录管理」，`sg-` 前缀 CSS/DOM，
纯 vanilla、无后端改：

- **CSS**（`<style>` 末，cg- 块之后）：`sg-*` 卡片/网格/分段/分类/详情浮层一套，全部沿用 console
  暗色 token（`--panel/--panel2/--line/--brand/--dim/--ink/--chip`），grid 用 `minmax(0,1fr)`（承 WB-099）。
- **JS**：`skillsCat` 改为派发器（子切换）；原 CRUD 迁为 `skillsManage`（3 处递归刷新改指自身）；
  新增 `skillsGallery`（搜索框 + 派发浏览/搜索）、`sgBrowse`（精选 + 推荐/SkillHub/套件分段）、
  `sgFeatured`（SKILLHUB_FEATURED，空则静态兜底，换一换轮换）、`sgReco`（SK_GRID）、`sgKits`（静态套件）、
  `sgSkillhub`（skill 镜像 + skill-category chips，空则静态 SG_GRID/SG_CATS 兜底）、`sgSearch`（skills/search CLI 代理）、
  `sgDetail`（只读浮层：图标/分类·来源徽章/★⬇/简介/标签/skillhub.cn 链接）。静态兜底数组 SG_FEATURED/SG_CATS/SG_GRID/SG_KITS。
- **不搬**：真安装/我安装的/SKILL.md 源码预览（Hub 门户无本地技能后端，`/api/skills/*` 属本地 App）——App 卡片右上「＋安装」在门户无意义，改为整卡点击开只读详情（诚实不做假动作）。

验证：
- `node --check` 内联 JS 语法通过。
- 运行时验证（Node vm + 最小 DOM shim，打真实 Hub :8100 数据，alice 平台管理员）：
  `skillsGallery/sgFeatured/sgSkillhub/sgReco/sgKits/sgDetail` 全部无异常；SkillHub 段渲染 **332 张真实镜像富卡**
  （★/⬇）+ 13 个分类 chips + skillhub.cn 链接；精选 1 卡 + 换一换；套件 4 卡；详情浮层正常。
- 浏览器实测：并发会话（WB-100/101）长时间独占共享 MCP 浏览器，遂用**独立 headless chromium + CDP**
  （ms-playwright 二进制 + Node 内置 WebSocket）截图验收，以 alice 平台管理员进目录运营中心 → 技能：
  - 浏览橱窗默认渲染：精选卡 + 换一换 + 推荐/SkillHub/套件三段 + 13 分类 chips + skillhub.cn 链接 +
    **332 张真实镜像富卡**（图标/名称/简介/⬇★/分类），暗色协调无「深底深字」。
  - 点卡片弹**只读详情浮层**（分类·来源徽章/★⬇/能力介绍/skillhub.cn，底部「Hub 门户为浏览视图」诚实说明）。
  - 子切换「目录管理」回原 SK_GRID CRUD（新增表单 + 列表 编辑/停用/删除），无回归。
  - `document.documentElement.scrollWidth == clientWidth`（1280），**无横向溢出**（承 WB-099）。
- 提交前敏感文件自检干净。
- 注：console.html 工作树同时叠着 WB-100/101 未提交改动，**本条不整文件提交**（真提交须按 hunk 只暂存 sg-/WB-102）。
