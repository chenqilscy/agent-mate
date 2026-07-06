---
id: WB-049
title: 我的专家 —— 自定义专家全栈（后端持久化 + 人格注入 + 前端创建/列表/召唤）
severity: P2
area: backend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/views/ExpertsView.tsx:161
  - backend/agent/experts.py:26
  - backend/agent/runtime.py:236
  - backend/storage/db.py:117
  - backend/storage/models.py:65
created: 2026-07-07
---

## 问题

专家页右上「我的专家」按钮只弹 toast（[ExpertsView.tsx:161-176](../../src/views/ExpertsView.tsx#L161-L176)），没有目标形态里的「我的专家」列表 / 空状态（"还没有创建任何专家 / ＋创建专家"）/ 创建流程。用户无法创建属于自己的专家。

要"真"（铁律：不硬编码不模拟），自定义专家必须**真持久化**且**真影响回答**：当前 `run_chat` 把 loadout 专家名逐个 `persona_for(name)` 注入系统提示（[runtime.py:236-239](../../backend/agent/runtime.py#L236-L239)），而 `persona_for` 只查静态字典 `EXPERTS`、查不到退化成通用人格（[experts.py:9-27](../../backend/agent/experts.py#L9-L27)）。没有自定义专家的存储与解析，创建的专家不会有真人格。

## 触发场景

专家页 → 点右上「我的专家」：只弹一条 toast，没有列表、没有空状态、无法创建。即便手动把某个自造名字加进 loadout，后端也只给通用人格，无法体现自定义专长。

## 影响

P2：「我的专家/创建专家」整块缺失。做实需新增后端表 + 路由 + 人格解析（owner 维度），是本功能里唯一的后端改动。projects 表已是 owner 维度存 `experts[]`（[db.py:117-129](../../backend/storage/db.py#L117-L129)），照此模式扩展即可。

## 建议修法

### 后端
- `storage/db.py`：新增 `experts` 表（`id/owner_id/name/subtitle/avatar/intro/persona/tags/created_at`），加 `create_expert / list_experts / get_expert / delete_expert`；沿用幂等建表（`CREATE TABLE IF NOT EXISTS` + 必要时 `_migrate`）。
- `storage/models.py`：新增 `Expert` 模型。
- `routers/experts.py`（新）：`POST /api/experts`、`GET /api/experts`、`DELETE /api/experts/{id}`，owner 维度（复用 `auth` 依赖）；`main.py` 挂路由。
- `agent/runtime.py`：注入人格前，先查当前 owner 的自定义专家 `{name: persona}`，命中用自定义 persona，否则回退 `persona_for(n)`——一处小改让自定义专家真生效。

### 前端
- `stores/expertStore.ts`（新）：`list/create/remove` 调后端。
- `MyExpertsView`：「我的专家」列表 + 空状态（"还没有创建任何专家 / ＋创建专家"）；卡片支持召唤/删除。「我的专家」按钮改为打开该视图。
- `CreateExpertModal`（新，套 `.np-overlay/.np-modal`）：name / subtitle / emoji 头像 / intro / persona（指令）/ tags → `POST /api/experts`。
- 召唤自定义专家：同 WB-048，`startDraft` + loadout 设该专家名。

## 验证

- `npx tsc --noEmit` 通过；`backend/.venv/Scripts/python.exe -m py_compile` 改动的 .py 全过。
- 硬重启 :8000，手动跑创建 → 列出 → 召唤 → 发一条消息，确认回答带该自定义人格；删除后不再出现。
- Playwright：空状态 → 创建 → 列表出现 → 召唤回首页 loadout 已选中；**明暗双主题**；≤900px。
- owner 隔离：另一 owner 看不到（对齐 WB-013 方向，路由按 owner 过滤）。

## 处理记录（2026-07-07）

- 改动：
  - 后端：
    - `storage/models.py`：新增 `Expert` dataclass（id/owner_id/name/subtitle/avatar/intro/persona/tags/created_at/updated_at）。
    - `storage/db.py`：新增 `experts` 表（`CREATE TABLE IF NOT EXISTS` + owner 索引，老库 startup 自动建、无需迁移）与 `create_expert/list_experts/get_expert/delete_expert`（owner 维度，字段截断上限）；import 增 `Expert`。
    - `routers/experts.py`（新）：`GET/POST /api/experts`、`DELETE /api/experts/{id}`，全部按 `current_user` 过滤；persona 留空用 intro 兜底。`main.py` import 并 `include_router`。
    - `agent/runtime.py`：注入专家人格前先建 `{name: persona}`（`db.list_experts(user.id)` 且 persona 非空），命中优先、否则回退 `persona_for` —— 让自造专家真影响回答。
  - 前端：
    - `lib/types.ts` 增 `CustomExpert`；`lib/api.ts` 增 `listExperts/createExpert/deleteExpert`。
    - `stores/expertStore.ts`（新）：`load/create/remove`。
    - `components/expert/CreateExpertModal.tsx`（新，套 `.np-*` 弹窗/表单类）：头像/名称/职称/能力介绍/人格指令/标签。
    - `views/ExpertsView.tsx`：新增 `MyExpertsPane`（复用 `.auto-empty*` 空态 + `.ecard` 卡片，召唤/删除）；「我的专家」按钮打开该子视图，任意 tab 切换退回目录。
- 验证：`npx tsc --noEmit` 通过；`py_compile` 改动 .py 全过。**硬重启 :8000**（Windows reload 不生效）后：
  - `GET /api/experts` 返回 200（非 404），路由生效。
  - Playwright 端到端（:5180，登录用户「奇」）：空态 → 创建「海盗船长顾问」（人格：每句以「啊哈，船长！」开头、航海比喻）→ 卡片出现 → 召唤回首页 loadout 已挂该专家 → 发「给我一条控制现金流的建议」→ **真实 LLM 回答**：「啊哈，船长！盯紧你的藏宝箱……现金流不是看你捞了多少，而是看你口袋里的每一枚金币能不能撑到下一座金银岛！」聊天头显示「已加载 · 专家 海盗船长顾问」，trace 复述人格约束 —— **自定义人格真注入、真生效**。
  - 刷新后列表仍在（`load()` 从后端拉取，确认真持久化）；删除 → 回到空态（DELETE 生效）。测试专家已删除，未留库内脏数据。
  - **明暗双主题**：创建弹窗与空态在 `body.dark` 下深底浅字、对比正常（复用 `.np-*`/`.auto-empty*` 现成类，天然继承暗色覆盖）。
- commit：741ee24（与 WB-048 同一 commit）
