---
id: WB-036
title: 自动化编辑器向目标设计对齐（一期）：全屏编辑器骨架 + 工作空间绑定 + 模型选择
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/AutomationView.tsx:167
  - src/lib/types.ts
  - src/lib/api.ts
  - backend/routers/automations.py:34
created: 2026-07-06
---

## 问题

对照参考产品（腾讯 WorkBuddy v5.2.3）截图，本项目当时的自动化编辑体验明显更薄：

- 目标是**全屏编辑页**（面包屑「自动化 / <名称>」+ 右上「取消/保存」+ 右侧「运行历史」侧栏），
  当前只有一个 `.np-*` 小弹窗（[`AutomationView.tsx:167`](../../src/views/AutomationView.tsx#L167) `AutomationModal`）。
- 目标编辑器顶部有**工作空间**绑定与**模型选择**；当前弹窗都没有暴露，尽管后端**已支持**：
  `automations` 表已有 `project_id` / `model` 列（[`db.py:141`](../../backend/storage/db.py#L141)），
  scheduler 已把 `model=auto.model` 传给 `run_chat`（[`scheduler.py:38`](../../backend/agent/scheduler.py#L38)），
  创建路由 `CreateAutomationBody` 也已收 `project_id` / `model`（[`automations.py:23`](../../backend/routers/automations.py#L23)）。
  纯粹是前端没做入口，能力被埋没。
- 缺口附带：`UpdateAutomationBody`（[`automations.py:34`](../../backend/routers/automations.py#L34)）**没有** `project_id`，
  故「编辑既有自动化时改工作空间」这条路径后端不支持，需补上。

本 issue 只做**一期地基**：全屏编辑器骨架 + 工作空间绑定 + 模型选择。Loadout（技能/专家/连接器）、
频率扩展（周/月/单次 + 生效日期）、权限模式与微信推送为后续 issue，另行登记，不夹带。

## 触发场景

1. 「自动化」页点「新建」或点某模板 → 只弹出一个小弹窗，字段仅名称/指令/触发方式。
2. 无法为自动化选择「工作空间」（虽然后端 `project_id` 可用）。
3. 无法为自动化单独选择「模型」（虽然后端 `model` 已透传给 scheduler→run_chat）。
4. 想编辑一条既有自动化：当前根本没有编辑入口（卡片菜单只有 立即运行/打开上次运行/删除）。

## 影响

P2：功能可用但与目标设计差距大、且埋没了后端已具备的 project/model 能力；用户无法把自动化
绑定到某工作空间或指定模型。不涉及数据丢失或安全。

## 建议修法

- **前端**：把 `AutomationModal` 升级为 `AutomationView` 内的**全屏编辑器模式**（`editing` 状态：
  `{ id?: string; prefill?: … } | null`）。挂载编辑器时列表/模板隐藏，显示：
  - 面包屑「自动化 / <名称或“新建”>」+ 右上「取消 / 保存」（复用既有按钮 class）。
  - 名称、工作空间（下拉/多选 chip，数据来自 `projectStore`；一期先做**单选**映射到 `project_id`，
    UI 用既有 chip 样式，多选留待后续）、指令、模型选择（复用对话 composer 的模型选择器组件/数据源）。
  - 编辑既有项时，右侧「运行历史」侧栏用**既有** `api.listAutomationRuns`（WB-035 已有），
    逐条点开 → `openSession` + 切到 chat（复用 `.pop-item.hist-item` 或既有列表样式，不新增 CSS）。
  - 触发方式沿用现有 interval/daily（频率扩展是后续 issue）。
- **类型/接口**：`CreateAutomationInput` 增 `project_id?` / `model?`；`Automation` 视图类型补 `project_id?` / `model?`
  以便回填编辑；`api.createAutomation` / `updateAutomation` 透传新字段。
- **后端**：`UpdateAutomationBody` 增 `project_id: str | None`，`update_automation` 路由沿用 `model_dump(exclude_none=True)`
  即可落库（注意：置空/解绑工作空间的语义一期可不做，避免 `exclude_none` 把清空吞掉——先只支持设置/切换）。
- 严守铁律：复用既有 class 与 token，暗色走 `body.dark` 覆盖；不造假（工作空间/模型都真写库、真影响 scheduler 运行）。

非目标（另开 issue）：Loadout（技能/专家/连接器）、频率扩展（周/月/单次 + 生效日期区间）、
权限模式 + 完全访问确认弹窗、微信小程序推送。

## 验证

- `npx tsc --noEmit` 通过；`py_compile backend/routers/automations.py` 通过。
- 浏览器实测（明暗双主题）：
  - 新建：点模板 → 进入全屏编辑器 → 选工作空间 + 选模型 + 填指令 → 保存 → 列表出现该卡片；
    SQLite 侧 `automations` 行的 `project_id` / `model` 落库正确。
  - 编辑：卡片菜单「编辑」→ 进入编辑器且字段回填（含工作空间/模型）→ 改模型 → 保存 → 复查落库。
  - 运行历史侧栏：对一条跑过的自动化，编辑器右侧列出多次运行，点开 → 打开对应会话正文。
  - 真实性：编辑器选定模型后「立即运行」，该次会话确由所选模型产出（trace/模型标识可佐证）。
- 回归：取消不落库；模板预填仍生效；卡片菜单原有项（立即运行/打开上次运行/删除）不受影响；
  暗色主题下编辑器无「白底白字/深底深字」。

## 处理记录（2026-07-06）

- 改动：
  - `src/views/AutomationView.tsx` —— 把 `AutomationModal`（`.np-*` 小弹窗）替换为视图内**全屏
    `AutomationEditor`**：`editing: { auto?; prefill? } | null` 状态，非空时整页渲染编辑器、隐藏列表/模板。
    面包屑「<icon> 自动化 / <名称>」+ 右上 取消/保存（编辑态另加 立即运行/删除）；字段：名称（`.np-input`）、
    **工作空间**（`.np-row`+`.np-chip`+`.np-add`，弹 `Popover` 列 `projectStore` 项目单选→`project_id`，
    含「不绑定（默认工作区）」）、指令（`.np-ta`）、**模型**（复用 `.ctool.model` 按钮 + `Popover` 里 `.mrow`
    行选 `settingsStore.models`，落到 automation 自己的 `model` 字段，新建默认取全局 `settingsStore.model`）、
    触发方式（沿用 interval/daily）。编辑态右侧 `aside.auto-ed-side` 用**既有** `api.listAutomationRuns`
    （WB-035）列运行历史，逐条 `openSession`→chat。卡片「更多」菜单新增「编辑」项。
  - `src/styles/app.css` —— 新增一小块 `.auto-ed*` 布局类（面包屑、两栏 flex、侧栏），**仅用 border+token、
    无 `#fff`/`var(--ink)` 背景**，故明暗双主题天然安全；其余全复用既有类（均已确认有 `body.dark` 覆盖）。
  - `backend/routers/automations.py` —— `UpdateAutomationBody` 增 `project_id`；update 路由加与 create 同款
    **归属校验**（改绑到非自己项目 → 404）。`exclude_none` 语义下清空为 no-op（一期只支持设置/切换，见上文）。
  - `backend/storage/db.py` —— `_AUTOMATION_FIELDS` 补 `project_id`，否则 PATCH 的 project_id 会被静默丢弃。
- 验证：
  - `npx tsc --noEmit` 通过；`py_compile automations.py db.py` 通过。
  - 后端手测（curl）：create→PATCH `project_id`+`model`→GET 回读，`project_id`/`model` 均正确落库；
    坏 `project_id` PATCH → 404；`model` 存 picker 的 `Name[:id]` 串，与 `resolve_model` 一致。
    **注意**：后端 Windows 下 `reload=False`（`main.py`），改后端必须硬重启 `:8000` 才生效——本次首测因未重启
    出现 `project_id` 不落库假象，重启后正常。
  - Playwright 明暗双主题实测：
    - 新建：点「每日 AI 新闻推送」模板 → 全屏编辑器（名称/指令预填、模型默认全局）→ 选工作空间「咖啡创业」+
      改模型 GLM-5.2 → 保存 → 列表出现卡片；API 回读该 automation `project_id=咖啡创业id`、`model=GLM-5.2`。
    - 编辑：卡片「⋯→编辑」→ 字段回填、右侧「运行历史（1）· 36分钟前」侧栏正常，点开可跳会话；取消不落库
      （回归确认 `每日一个为什么` 仍 `model=None/project_id=None`）。
    - 暗色：编辑器、模型/工作空间 `Popover`、seg2、按钮均为深色面 + 亮字，无「白底白字/深底深字」。
    - 测试产物已清理（删除测试 automation、根目录截图、`.playwright-mcp`）。
- 非目标（后续 issue）：Loadout（技能/专家/连接器）、频率扩展（周/月/单次 + 生效日期区间）、
  权限模式 + 完全访问确认弹窗、微信小程序推送。
- commit：（尚未提交）
