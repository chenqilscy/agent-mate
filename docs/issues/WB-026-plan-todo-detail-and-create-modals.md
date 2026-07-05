---
id: WB-026
title: 计划 · 待办详情弹窗 + 新建待办弹窗 + WorkItem 数据模型扩展
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/components/project/ProjectWork.tsx:16
  - src/lib/types.ts:119
  - src/lib/api.ts:63
  - src/stores/workItemStore.ts:1
  - backend/routers/work_items.py:1
  - backend/storage/models.py:73
  - backend/storage/db.py:115
created: 2026-07-06
---

## 问题

「计划」看板（`ProjectWork.tsx:16` `KanbanBoard`）目前只是最小实现：

- 卡片只有 标题 + 负责人首字 + 相对时间；**点卡片没有详情弹窗**，无法查看/编辑描述、状态、负责人、截止日期、附件。
- 新建待办是**列内一行内联输入**（回车创建），只能填标题，无法在创建时带描述/附件/截止日期。
- 后端 `WorkItem`（`models.py:73` / `db.py:115` 建表）**只有** `title/status/source/assignee`，**缺** `description`、`due_date`、`attachments` 字段，PATCH（`work_items.py:69`）只接受 `title/status`。

目标设计（用户截图）里，待办有完整的「待办详情」弹窗与「新建待办」弹窗（标题+描述+附件〔本地文件/项目资产〕+截止日期），当前实现离该设计差距很大。

## 触发场景

进入任一项目 → 计划 tab → 点某张卡片：无任何反应（期望：打开待办详情）。点「＋ 新建待办」：只弹出列内单行输入，无法填描述/截止日期/附件。

## 影响

P2：核心信息（描述、截止日期、附件）无处承载，计划模块只能当纯标题清单用，达不到目标设计的可用度。非阻断既有流程。

## 建议修法

**后端（数据模型先行）**
- `models.py` `WorkItem` 增 `description: str = ''`、`due_date: str | None = None`、`attachments: list[dict] = field(default_factory=list)`。
- `db.py`：建表语句补三列；`init_db()` executescript 之后加**幂等迁移**（`PRAGMA table_info(work_items)` 判断缺列 → `ALTER TABLE work_items ADD COLUMN …`），兼容老库。`create_work_item`/`update_work_item`/`_row_to_work_item` 读写新列（`attachments` 存 JSON 文本）。
- `work_items.py`：`CreateWorkItemBody` 增可选 `description`/`due_date`/`attachments`；`UpdateWorkItemBody` 增 `description`/`due_date`/`attachments`；`_view` 透传。

**前端**
- `types.ts` `WorkItem` 补 `description`/`due_date`/`attachments`；`api.ts` `createWorkItem`/`updateWorkItem` 参数放开；`workItemStore` 补一个通用 `update(id, patch)`。
- **待办详情弹窗**：点卡片打开，复用 `.np-overlay/.np-modal` 或原型的卡片式弹窗风格；描述可编辑、状态下拉（待开始/进行中/已暂停/已完成）、截止日期、附件列表、「添加到输入框」（把标题+描述塞进项目 Composer 输入 — 复用 composer 的入口，不新造协议）。
- **新建待办弹窗**：替换列内内联输入为独立弹窗，标题+描述+附件选择器（本地文件走 file input；项目资产走 `AssetsManager` 同源的项目文件列表）+ 截止日期。
- 附件「项目资产」引用项目云盘文件，只存引用（name/path），不复制文件；不伪造上传成功。
- 视觉零重设计：沿用既有 class 与 token，暗色走 `body.dark` 覆盖。

## 验证

- `cd backend && ./.venv/Scripts/python.exe -m py_compile storage/db.py storage/models.py routers/work_items.py`
- 删旧库或用既有库都能起（迁移幂等）；`npx tsc --noEmit` 过。
- 浏览器实测：新建带描述+截止日期+附件的待办→持久化（刷新后仍在）；点卡片打开详情、改描述/状态/截止日期→PATCH 成功、刷新保留；「添加到输入框」把内容注入 Composer。
- **明暗双主题**都看一遍两个弹窗，无白底白字/深底深字。

## 处理记录（2026-07-06）
- 改动：
  - 后端 `models.py` `WorkItem` 增 `description/due_date/attachments`；`db.py` 建表补三列 + 幂等迁移 `_migrate_columns()`（`PRAGMA table_info` → `ALTER TABLE ADD COLUMN`），`create/update/_row_to_work_item` 读写新列（attachments 存 JSON）；`routers/work_items.py` create/update body 放开新字段，`_clean_attachments` 白名单化引用（限 20 个），PATCH 用 `model_fields_set` 区分 `due_date` 显式清空 vs 不改，create 加 owner 校验。
  - 前端 `types.ts` `WorkItem`+`WorkAttachment`（+created_at/updated_at）；`api.ts` create/update 参数放开；`workItemStore` `add` 改对象入参并返回 WorkItem、新增 `update`；`uiStore` 加一次性 `composerPrefill`+`setComposerPrefill`，`Composer` effect 消费注入输入框。
  - `ProjectWork.tsx` 重写 `KanbanBoard`：待办详情弹窗（描述编辑/状态·截止日期下拉/附件/「添加到输入框」）、新建待办弹窗（标题+描述+附件〔本地文件上传到项目云盘 / 项目资产引用〕+截止日期）、卡片显示描述预览+附件/截止徽标。样式复用既有 class，新类仅用主题变量（`app.css` 追加 `.wb-*`）。
- 验证：`npx tsc --noEmit` 过；`py_compile` 过；API 冒烟（create 带描述/截止/附件→落库、PATCH 改状态+清空截止+改描述、attachments 白名单化）；Playwright 实测新建→详情→改描述/状态/截止→「添加到输入框」注入 Composer→刷新持久化，明暗双主题弹窗均可读。
- commit：（待用户确认提交）
