---
id: WB-128
title: 模型管理重构 —— 内置改「厂商渠道」（真实 base/模型，填 key 即用）+ 移除假 Auto，自定义作兜底
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/storage/provider_seed.py
  - backend/storage/db.py
  - backend/agent/llm.py
  - backend/agent/runtime.py:113
  - backend/routers/models.py
  - src/components/composer/ModelConfigModal.tsx
  - src/components/composer/ModelPicker.tsx
  - src/lib/api.ts
  - src/lib/types.ts
created: 2026-07-12
---

## 问题

WB-124 把「配置自定义模型」做成了真功能，但**内置模型那一列仍是原型抄来的假数据**
（Auto / Hy3 preview / GLM-5.2 + 假倍率/「限时折扣」/「高」标签）。且 `resolve_model_config`
里**任何内置项（含 Auto）都回退 `.env` 那一个模型**——「Auto」没有任何自动选模型/路由逻辑，
纯摆设（违反铁律#1）。

## 建议修法（用户已定方案）

把「内置模型」从假的一列模型名，改成**真的一批厂商渠道**：
- 预置真实厂商（DeepSeek / 智谱GLM / MiniMax / 月之暗面Kimi / 通义Qwen / OpenAI），每个自带
  **确认过的 base_url + 对外真实模型名**；用户对某厂商填一次 **API Key** → 其模型即可选、真调用。
- 厂商模型可增删（上新/清理）；Key 只后端存、按 owner 隔离、绝不回前端（铁律#4）。
- **移除 Auto** 与假倍率；`.env` 模型作 local-first 兜底，如实呈现为「默认 · <model>」。
- 保留 WB-124 的「自由填写自定义模型」作预置外兜底（自建/代理站）。

个别厂商端点非标准 `/chat/completions`（MiniMax = `/text/chatcompletion_v2`）→ 加 `chat_path`
字段保证真能通。

## 验证

- tsc / vite build / py_compile 过。
- 后端 TestClient：厂商列表、设/撤 key、加/隐藏/删模型、custom CRUD、脱敏（响应无 key 明文）。
- `resolve_model_config`：`@provider:model` + 有 key → 该厂商 base/key/chat_path；无 key/未知 → .env 兜底；
  自定义名 → 其 base/key；空 → .env。用 mock 校验 stream_chat 真按 base+chat_path 拼 URL。
- Playwright 明暗双主题：厂商卡片展开填 key → 其模型进 picker；加/隐藏模型；自定义兜底增删；DB 收尾清干净。

## 处理记录（2026-07-12）

- **后端**
  - 新 `storage/provider_seed.py`：6 家真实厂商注册表（id/name/base_url/chat_path/icon/color/key_hint/site/models）。
    MiniMax 用 `chat_path=/text/chatcompletion_v2`（非标准端点）保证真能通。
  - `db.py`：加 `provider_keys`(owner,provider→key，脱敏只给 has_key) + `provider_models`(hidden=隐藏预置/hidden=0非预置=新增) 表 + CRUD。
  - `llm.py`：`stream_chat` 加 `chat_path`，`url = {base}/{chat_path}`。
  - `runtime.py`：`resolve_model_config` 支持 `@{provider}:{model}` → 该厂商 base/key/chat_path；无 key/未知/空 → `.env` 兜底；返回 4 元组含 chat_path，调用处透传。
  - `routers/models.py`：GET 重组为 `{default, effective, providers[], custom[], models[]}`（models 扁平供 picker：默认兜底 + 有 key 厂商模型 + 自定义）；
    移除假 `_BUILTIN`/Auto/倍率、`hide-builtin` 端点；加 `PUT /providers/{id}/key`、`POST /providers/{id}/models`、`POST /providers/{id}/models/hide`；保留 WB-124 custom CRUD。
- **前端**
  - `types.ts`：ModelOption 改 `key`(选择键)/group('default'|'provider'|'custom') + 新 `Provider`/`ProviderModel`/`ModelsResponse`。
  - `api.ts`：models() 返回 ModelsResponse；加 setProviderKey/addProviderModel/hideProviderModel；去掉 hideBuiltinModel。
  - `ModelPicker.tsx` 重写：默认兜底 + 按厂商分组只显有 key 的模型 + 自定义 + 配置模型；去掉假 Max/倍率/标签。
  - `ModelConfigModal.tsx` 重写：厂商可折叠卡片（key 输入/保存/撤销 + 预置模型隐藏·恢复 + 补充模型 + Base/获取 Key 链接）+ 自定义兜底增删改。
  - `Composer.tsx`：模型按钮显示友好名（key→name），不再显示裸 key。`settingsStore` 默认 model '' + reloadModels。`app.css` 加 `.mc-prov*` 等类。
- **验证**
  - `npx tsc --noEmit` ✓；`vite build` ✓；`py_compile` 五个 .py ✓。
  - 隔离 scratch DB + TestClient + mock httpx：6 厂商列表 / 设·撤 key / 加·隐藏·删模型 / 脱敏(响应无 key 明文) /
    `@provider` 路由到真实 base·key·chat_path / MiniMax 非标 path / 无 key·空→.env 兜底 / `stream_chat` URL=base+chat_path —— 全断言过。
  - 硬重启 live :8000 后 Playwright 明暗双主题 E2E：picker 显「默认·deepseek-v4-pro」无假项；展开 DeepSeek 填 key→已启用+模型进 picker(不泄漏)；
    隐藏 reasoner·加 coder→picker 反映；选 deepseek-chat→按钮显名+localStorage 存 `@deepseek:deepseek-chat`；DB 收尾清干净。
- commit：（待用户确认时提交）

