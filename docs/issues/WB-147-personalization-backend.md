---
id: WB-147
title: 个性化真后端 —— 回复风格预设 + 自定义指令（按 owner 存 KV，注入 agent 系统提示真生效）
severity: P1
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/personalization.py
  - backend/routers/prefs.py
  - backend/agent/runtime.py:247
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

WB-146 搭好设置中心外壳后，「个性化」tab 的「基本风格和语调 / 自定义指令」还是「即将上线」占位。
这是设置中心里**最能做成真生效**的一项：用户选的回复风格 + 自定义指令，应当真持久化并**注入到 agent
系统提示**，影响之后所有对话（对齐高保真原型「个性化」页）。

（注：截图「系统设置」里的显示语言/字体大小/加载欢迎语等，前端当前**无 i18n、无 rem 字体缩放、无 loading-hints
机制**，硬接后端只会得到「存了但不生效」的假开关，违反铁律#1，故本条不做那些，留作后续基建 issue。）

## 触发场景

设置 → 个性化 → 选「专业严谨」或填自定义指令「每次回答前先说 ok」→ 保存 → 新开对话，
agent 的回复风格/前缀应真的变化。刷新/重开应用后设置仍在。

## 影响

P1：这是设置中心第一条打通「设置 UI → 后端持久化 → agent 真生效」的全栈竖切，为记忆/其余偏好铺样板。

## 建议修法

1. **后端 `agent/personalization.py`**：`STYLE_PRESETS`（key/label/desc/prompt，8 档对齐原型）+
   `build_personalization_prompt(owner)`（读 `user_settings` KV 的 `pref.style`/`pref.custom_instructions`，
   拼「# 个性化偏好」段；无则空串）。复用现成 `db.get_user_setting/set_user_setting`（KV 表已存在）。
2. **`agent/runtime.py`**（~247，system_extra 之后）注入：`system_prompt += build_personalization_prompt(user.id)`，
   全模式（exec/plan/ask）生效。
3. **路由 `routers/prefs.py`**（模块名避开 `config.settings` 命名冲突）：`GET/PUT /api/settings`，
   owner=`current_user().id`；GET 返回 {style, custom_instructions, style_presets}；PUT 收部分字段、
   校验 style 合法性、自定义指令截断上限。`main.py` 注册。
4. **前端**：`api.settings()/saveSettings()`；`SettingsModal` 个性化 panel 用真控件替占位——
   风格下拉（读 style_presets）+ 自定义指令 textarea + 保存，复用 `np-input/np-ta` 等既有 class。

## 验证

- `py_compile` 后端改动文件；`tsc --noEmit` + 需要时 `vite build`。
- 真跑一轮对话验证「自定义指令」真生效（如指令要求固定前缀，看回复是否带）。
- 明暗双主题看个性化 panel。

## 处理记录（2026-07-14）

- 改动：
  - 新增 `backend/agent/personalization.py`：`STYLE_PRESETS`（8 档，对齐原型）+ `get_personalization(owner)` + `build_personalization_prompt(owner)`（读 KV → 拼「# 个性化偏好」段）；复用现成 `db.get_user_setting/set_user_setting`（`user_settings` 表已存在，无需迁移）。
  - 新增 `backend/routers/prefs.py`：`GET/PUT /api/settings`（模块名 prefs 避开 `config.settings` 命名冲突）；owner=`current_user().id`；PUT 校验 style 合法性、自定义指令 trim+2000 上限、空值删键。
  - `backend/agent/runtime.py`：import `build_personalization_prompt`，在 system_extra 之后 `system_prompt += build_personalization_prompt(user.id)`，全模式（exec/plan/ask）生效。
  - `backend/main.py`：注册 `prefs.router`。
  - 前端 `src/lib/api.ts`：`api.settings()/saveSettings()`；`src/lib/types.ts`：`StylePreset`/`AppSettings`。
  - `src/components/settings/SettingsModal.tsx`：抽出 `PersonalizePanel`——外观切换 + 8 张风格卡（读后端 style_presets，选中绿高亮）+ 自定义指令 textarea（`np-ta`）+ 保存（dirty 才可点）；替掉原「即将上线」占位。
  - `src/styles/app.css`：`set-flabel/set-fsub2/set-styles/set-style*` 样式（token 化，暗色安全）。
  - **未做（诚实）**：截图「系统设置」的显示语言/字体大小/加载欢迎语——前端无 i18n、无 rem 缩放、无 loading-hints 机制，硬接会成假开关，留后续基建 issue。
- 验证：
  - `py_compile` 四个后端文件过；`tsc --noEmit` 过。
  - 后端重启（Windows reload=False）后 `GET /api/settings` 返回 8 档 preset；`PUT` 持久化并回显。
  - **真生效端到端**：PUT 自定义指令「首行原样输出 WB147-OK-喵」→ ask 模式真跑一轮 → 回复首行确含 `WB147-OK-喵`（模型遵循，证明注入生效，铁律#1）。
  - 前端（MCP 浏览器被并发会话占用 → 独立 headless chromium + CDP）：个性化 panel 加载出已存值（风格=专业严谨、自定义指令文本），**明暗双主题**截图核对渲染无坑、选中态绿高亮正常。
  - 测试后已把设置**清回 default/空**，不残留影响用户真实对话。
- commit：未提交（用户未要求）。
- 后续：记忆（真持久化 + 注入 + 可选 LLM 抽取）另开 issue，复用本条的 KV + 注入样板。
