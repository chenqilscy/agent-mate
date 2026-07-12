---
id: WB-132
title: 模型能力/成本元数据管理（为 Auto 模式铺路）+ 接入地址简化为仅 Base URL
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/storage/db.py
  - backend/routers/models.py
  - src/components/composer/ModelConfigModal.tsx
  - src/components/composer/ModelPicker.tsx
  - src/lib/api.ts
  - src/lib/types.ts
created: 2026-07-12
---

## 问题 / 诉求

1. **接入地址过繁**：WB-129 加的「请求路径(chat_path)」输入框用户用不到——只需 Base URL 可改即可
   （非标端点如 MiniMax 由后端 seed 兜底，用户不必管）。
2. **缺模型能力/成本管理**：想给每个模型记「支持文本/图片/音频/视频 + 工具调用 + 推理」等能力，
   以及「使用成本（每百万 token 输入/输出单价）+ 上下文长度」，为后续 **Auto 模式**（按能力匹配 + 成本权衡选模型）铺路。
3. **入口太隐蔽**：模型管理弹窗现只能从输入框模型下拉 →「配置模型」进，想要一个独立菜单入口（全局可达）。

## 方案（用户已定）

- **能力**：多标签 = 模态(text/image/audio/video) + tools(工具调用) + reasoning(推理)。
- **成本**：精确单价（每百万 token 输入价 + 输出价，数值）+ 可选上下文长度(context_window)。
- **来源**：用户手填 + 预置默认。能力按模型名给启发式默认（可编辑）；**价格不瞎编、默认留空由用户填**（铁律#1）。
- 按 owner + model_ref（选择键 `@provider:model` 或自定义名）持久化。
- UI：接入地址去掉 chat_path 输入（仅 Base URL）；每个模型加「能力」内联编辑（勾选 + 单价）+ 能力徽标摘要。

## 验证

- tsc / py_compile 过。
- TestClient：PUT meta 存/读；GET 附有效 meta（存储∨启发式默认）；reset 回默认；名字启发式(o1/reasoner→推理, 4o/vl→图片)。
- Playwright：接入地址只剩 Base URL；给某模型勾能力+填单价→保存→重开仍在；徽标显示；Auto 所需数据齐备。

## 处理记录（2026-07-12）

- **后端**
  - `db.py`：加 `model_meta`(owner, model_ref → capabilities JSON / input_cost / output_cost / context_window / note) 表 + get/list/set/delete。
  - `models.py`：`CAPABILITIES` 白名单 + `_default_capabilities`(按模型名启发式：默认 text+tools；名字含 4o/vl/vision… → image；含 reasoner/o1/o3/r1/qwq… → reasoning；**已避开裸 "-v" 误命中版本号**) + `_effective_meta`(存储∨默认，带 source)；
    GET 给每个厂商模型/自定义模型附 meta；`PUT /models/meta`(白名单过滤能力；reset=清覆盖回默认)。
- **前端**
  - `types.ts` 加 `ModelMeta` + ModelOption/ProviderModel 挂 meta；`api.ts` 加 setModelMeta/resetModelMeta。
  - `uiStore` 加全局 `modelConfigOpen` flag；**模型管理提到全局**：`Sidebar` 账号菜单加「模型管理」项 + 渲染 `ModelConfigModal`（复刻 HubConnectModal 模式）；`Composer` 改用同一 flag（去局部 state）。
  - `ModelConfigModal`：接入地址**去掉 chat_path 输入、仅 Base URL**（chat_path 传 '' 由 seed 兜底）；每个模型加能力徽标 + 「能力」内联编辑器（6 能力 chip + 输入/输出单价 + 上下文 + 保存/恢复默认）。
  - `ModelPicker`：模型名后显能力小徽标（text 不显）。`app.css` 加 `.mc-caps/.mc-metaed/.mc-capchip/.mc-costrow/.mrow-caps`。
- **验证**
  - tsc ✓ / vite build ✓ / py_compile ✓。
  - 隔离 TestClient：启发式默认(chat=text+tools, reasoner+推理, 4o+图片, o1+推理) / PUT 存读 / 非法能力白名单过滤 / reset 回默认 / 自定义模型 meta —— 全断言过。
  - 硬重启 :8000 后 Playwright 明暗实测：**账号菜单→模型管理**开弹窗；接入地址仅 1 个 Base 输入(chat_path 已去)；
    给 deepseek-chat 勾图片+填 1.5/8/128000→保存→读回 source=custom→reset 回默认(DB 清干净)；徽标显示；启发式修正(v4 不再误判 image)。
- commit：（待用户确认时提交）

