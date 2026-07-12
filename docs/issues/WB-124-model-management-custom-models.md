---
id: WB-124
title: 模型管理 —— 自定义模型全栈（多厂商 base/key、DB 按用户隔离、内置项可隐藏、切换真生效）
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/routers/models.py
  - backend/agent/runtime.py:113
  - backend/agent/llm.py:43
  - backend/storage/db.py
  - src/components/composer/ModelPicker.tsx:49
  - src/stores/settingsStore.ts
  - src/lib/api.ts
  - src/lib/types.ts
created: 2026-07-12
---

## 问题

底部模型选择器（`ModelPicker.tsx`，截图那个「Max 模式 + 内置模型列表带倍率 + 自定义模型分组 +
配置自定义模型」下拉）UI 骨架已在，但**只是摆设**：

1. **「配置自定义模型」按钮是空 toast**（`ModelPicker.tsx:49`），无法增删改自定义模型。
2. **自定义模型是硬编码**（`backend/routers/models.py` 的 `_CUSTOM` 两行），不可持久化、不按用户隔离。
3. **切换不真正生效**：`resolve_model`（`runtime.py:113`）只对 `"显示名:真实id"` 格式取冒号后的 id，
   且 `stream_chat`（`llm.py:43`）**永远用同一套 `.env` 的 `LLM_API_BASE`/`LLM_API_KEY`** —— 无法接入
   不同厂商（各自的 base URL + key）。
4. **内置项不可管理**：用不到的内置项无法从列表隐藏。

## 触发场景

打开底部模型下拉 → 点「配置自定义模型」→ 只弹一个 toast，什么都做不了；即便选了某个内置模型，
后端实际仍跑 `.env` 的 `LLM_MODEL`，换不成别的厂商/模型。

## 影响

模型管理是 local-first 应用的核心能力之一（用户自带 key 接不同厂商）。当前完全不可用，属功能缺失。P2。

## 建议修法（用户已定方案：完整多厂商 + DB 按用户隔离 + 内置可隐藏）

**后端**
- `db.py`：新表 `custom_models`（`id/owner_id/name(显示名,唯一 per owner)/model_id/api_base/api_key/
  icon/color/mult/sort/created_at/updated_at`）+ `hidden_builtin_models`（`owner_id,name` 联合主键）。
  CRUD 函数：list/get/create/update/delete custom；list/set hidden。**`api_key` 绝不回传前端**（铁律#4）——
  列表只给 `api_base` + `has_key: bool`。
- `routers/models.py`：`GET /api/models`（picker：可见内置−隐藏 + DB 自定义，脱敏）；`?all=true`（配置弹窗：
  含隐藏内置，带 `hidden` 标记）；`POST /api/models/custom`、`PATCH /api/models/custom/{id}`（空 api_key = 保持不变）、
  `DELETE /api/models/custom/{id}`、`POST /api/models/builtin/hide`（{name,hidden}）。全 `current_user()` 按 owner。
- `runtime.py`：`resolve_model` → `resolve_model_config(owner_id, client_model) -> (model_id, api_base, api_key)`：
  先按 DB 自定义模型 name 匹配（取其 base/key），否则 `":"` 旧格式回退（默认 base/key），否则内置 → `.env`。
- `llm.py`：`stream_chat` 加可选 `api_base`/`api_key` 覆盖参数。

**前端**
- `types.ts`：`ModelOption` 加 `id?/custom?/apiBase?/hasKey?/hidden?`。
- `api.ts`：createCustomModel/updateCustomModel/deleteCustomModel/hideBuiltin + models 支持 all。
- 新组件 `ModelConfigModal.tsx`：复用 `.np-overlay/.np-modal/.np-lbl/.np-input` 表单范式，管理自定义模型
  （显示名/model id/api base/api key/图标/倍率）+ 隐藏·恢复内置项。
- `ModelPicker.tsx:49`：把 toast 换成打开配置弹窗；隐藏的内置项不出现在 picker。
- `settingsStore.ts`：加 reloadModels。

## 验证

- `npx tsc --noEmit` 过；`py_compile` 改动的 .py 过。
- 手动：加一个自定义模型（填真实厂商 base/key/model）→ 在 picker 选它 → 发一条消息，SSE 真用该厂商回复
  （非 `.env` 默认）。删除、编辑（空 key 保持不变）、隐藏/恢复内置项都生效。
- 明暗双主题看配置弹窗；`GET /api/models` 响应里**绝无 api_key 明文**。

## 处理记录（2026-07-12）

- **后端**
  - `db.py`：加 `custom_models`（unique(owner_id,name)）+ `hidden_builtin_models` 表；CRUD
    `list/get/get_by_name/create/update/delete_custom_model` + `list_hidden_builtins/set_builtin_hidden`。
    `_row_to_custom_model(include_secrets)` 默认脱敏（剔 api_key，给 has_key）。
  - `llm.py`：`stream_chat` 加 `api_base`/`api_key` 覆盖参；无覆盖时回退 `.env`。
  - `runtime.py`：`resolve_model` → `resolve_model_config(owner_id, client_model) -> (model_id, api_base, api_key)`；
    调用处按 owner 解析一次、传给 `stream_chat`。
  - `routers/models.py`：`GET /api/models`（picker 可见项）+`?all=true`（含隐藏，带 hidden 标记）；
    `POST/PATCH/DELETE /api/models/custom`、`POST /api/models/builtin/hide`；全 `current_user()` 按 owner，重名 409。
- **前端**
  - `types.ts` `ModelOption` 加 id/model_id/api_base/has_key/builtin/hidden + 新 `CustomModelInput`；
    `api.ts` 加 create/update/delete/hide + models(all)；`settingsStore` 加 `reloadModels`。
  - 新 `ModelConfigModal.tsx`（套 `.np-*` + `mc-` 前缀，token 化天然暗色）：自定义模型增删改 + 内置隐藏/恢复。
    `ModelPicker.tsx` 「配置自定义模型」toast→`onConfigure`（弹窗提到 Composer，popover 关闭不影响）。
  - `app.css` 加 `.mc-*` 块。
- **验证**
  - `npx tsc --noEmit` ✓；`py_compile` 四个 .py ✓；`npx vite build` ✓。
  - 隔离 scratch DB + FastAPI TestClient 冒烟：CRUD / 脱敏（`sk-SECRET` 不出现在任何响应）/ 重名 409 /
    PATCH 留空 api_key 不清空 / 隐藏内置 picker 消失·?all=true hidden=true / DELETE + 二次 404 —— 全断言过。
  - `resolve_model_config`：选自定义 → 取到其 base/key/model_id；选内置 → (`.env` model, None, None)。
  - 硬重启 live :8000（reload 未生效的老坑）后 curl 真 CRUD + 无 key 泄漏。
  - Playwright 真机 E2E（:5174）：底部模型下拉→配置自定义模型→模型管理弹窗；**明暗双主题**均无白底白字/深底深字；
    新建带独立 base/key 的模型→列表现 🔑（has_key）→ 隐藏 GLM-5.1 picker 即消失 → 恢复 → 删除；DB 收尾清干净。
- commit：（待用户要求时提交）

