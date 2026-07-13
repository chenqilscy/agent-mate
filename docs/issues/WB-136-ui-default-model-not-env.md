---
id: WB-136
title: 「默认模型」改为在「配置模型」里选择，不再从 .env 读取
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/routers/models.py:154
  - backend/agent/runtime.py:113
  - src/components/composer/ModelConfigModal.tsx:345
  - src/components/composer/ModelPicker.tsx:39
  - src/App.tsx:65
  - src/stores/settingsStore.ts:39
created: 2026-07-14
---

## 问题

当前「默认模型」（模型菜单里 `key=""` 的那条「默认 · xxx」、以及未显式选模型时实际运行的模型）
唯一来源是后端 `.env` 的 `LLM_MODEL`：

- 展示：[backend/routers/models.py:159](../../backend/routers/models.py#L159) 的 backstop 直接 `name=f"默认 · {settings.LLM_MODEL}"`。
- 运行时解析：[backend/agent/runtime.py:148](../../backend/agent/runtime.py#L148) 的终点 `return settings.LLM_MODEL, None, None, default_path`，
  空选择（跟随默认）与「厂商选了但没 key」都落到 `.env`。

用户无法在 UI 里决定「未显式选模型时用哪个」，只能改 `backend/.env` 再重启后端——不符合本机可配置的预期。

## 触发场景

用户配了多个厂商（如 DeepSeek + 智谱），想把「智谱 glm-4.7」设为默认（新会话/未选模型时就用它）。
现在做不到：默认永远是 `.env` 的 `LLM_MODEL`，除非去改 `.env` 文件并重启后端。

## 影响

P2：功能缺口 + 反直觉。不影响现有已选模型的会话，但「默认」不可自助配置。
决策（与用户确认）：**彻底不读 `.env` 作默认**（牺牲零厂商配置时的开箱即跑），默认 100% 由 UI 决定；
默认选择**持久化到后端 DB、按 owner 隔离**。

## 建议修法

**后端**
- `storage/db.py`：新增通用 `user_settings(owner_id, key, value, updated_at)` KV 表 + `get/set_user_setting`；
  再包一层 `get_default_model(owner_id)->str` / `set_default_model(owner_id, ref)`（key=`default_model`）。
- `routers/models.py`：
  - `list_models` 读 `default_model`，校验它仍指向可运行模型（厂商有 key ∨ 自定义），失效则自愈清空；
    backstop 那条 `name` 改成 `默认 · <所选模型名>`（未设置则「默认（未设置）」）；响应加 `default_model` 字段，去掉 `.env` 派生的 `effective`/`default`。
  - 新增 `PUT /api/models/default {model_ref}`（''=清除），校验 ref 合法。
  - 便利：保存某厂商 key 且当前无默认时，自动把默认设为该厂商第一个可见模型（替代 App.tsx 首屏自动选）。
- `agent/runtime.py` `resolve_model_config`：空选择先取 DB 默认；无默认 → `raise LLMError("还没有设置默认模型…")`；
  终点兜底不再回 `.env`，改为 `raise LLMError("模型不可用…请重新选择默认模型")`（自定义模型仍可留空凭据走 .env，属其自身既有设计，不动）。

**前端**
- `App.tsx`：删掉「首屏用 `r.default` 回填 localStorage」的 seeding（改由 DB 默认承担）。
- `lib/types.ts` `ModelsResponse`：`default`/`effective` → `default_model`。
- `lib/api.ts`：加 `setDefaultModel(ref)`。
- `ModelConfigModal.tsx`：每个可运行模型（厂商有 key 的模型 + 自定义模型）加「设为默认／取消默认」，当前默认打徽标；
  底部提示文案从 `.env` 改成描述所选默认。
- `ModelPicker.tsx`：顶部「默认」条名字由后端给（无需逻辑改）。

## 验证

- `npx tsc --noEmit` 过；`py_compile` 改动的 .py 过。
- 配了厂商 key 后，在「配置模型」把某模型设为默认 → 模型菜单顶部「默认 · <该模型>」；新会话不选模型直接发，后端实际用该模型（看 loadout/trace）。
- 撤销该默认模型所属厂商 key → 列表自愈（默认清空），未选模型时发消息得到「未设置默认模型」的诚实报错，而非静默用 .env。
- 明暗双主题看「配置模型」弹窗的「设为默认」按钮/徽标样式协调（复用既有 mc-*/np-* class）。

## 处理记录（2026-07-14）

- 改动：
  - 后端 `storage/db.py`：新增 `user_settings(owner_id,key,value)` KV 表 + `get/set_user_setting`、`get/set_default_model`。
  - 后端 `routers/models.py`：`list_models` 读 DB 默认并对失效 ref 自愈清空，backstop 名字改为 `默认 · <所选>`／`默认（未设置）`（图标 ⚙️→⭐），响应 `default`/`effective` → `default_model`；去掉 `settings` import；新增 `PUT /models/default`（`_resolve_runnable_name` 校验合法性）；`set_provider_key` 在无默认时自动设为该厂商首个可见模型。
  - 后端 `agent/runtime.py` `resolve_model_config`：空选择先取 DB 默认，无默认 → `LLMError`；终点兜底不再回 `.env`，改 `LLMError`（自定义/legacy 仍可留空凭据走 .env，未动）。
  - 前端 `App.tsx` 删首屏 `r.default` 回填；`lib/types.ts` `ModelsResponse` 改字段；`lib/api.ts` 加 `setDefaultModel`；`ModelConfigModal.tsx` 每个可运行模型加「设为默认／取消默认」+「默认」徽标 + 改底部提示；`styles/app.css` 加 `.mc-tag.on`（填充 `--brand-600`，双主题安全）。
- 验证：
  - `npx tsc --noEmit` ✅、`npx vite build` ✅、`py_compile` 三个 .py ✅。
  - 硬重启 `:8000`（reload 未生效，serving stale code）。API 实测：`PUT /models/default @zhipu:glm-4.7` → ok；GET 回显 `默认 · glm-4.7`；非法 ref（无此模型/厂商无 key）→ 400 诚实报错。
  - 运行时 `resolve_model_config` 直测：空选择→解析到 DB 默认（glm-4.7 + 智谱 base/key）；显式 deepseek→具体；清默认后空选择→「还没有设置默认模型」LLMError；失效 ref→「模型不可用」LLMError；自动设默认组合逻辑→ `@deepseek:deepseek-v4-flash`。测后已把用户默认复原为 `@zhipu:glm-4.7`，未破坏其环境。
  - 前端 UI：Playwright 浏览器被并发会话独占，未能截图；改动仅复用既有 `mc-act(.on)`/`mc-tag` 类，新增 `.mc-tag.on` 用固定品牌绿 `--brand-600`（暗色无覆盖）配白字，与既有 `.add-btn.on`/头像同款，双主题安全、无铁律#3 风险。
- commit：（未提交，待用户指示）
