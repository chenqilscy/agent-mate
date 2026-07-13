---
id: WB-134
title: 内置厂商按官方文档建准确「能力+定价」默认表 + 定价 schema 扩展（缓存命中价/币种）+ 更新过时 seed 模型名
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/storage/provider_seed.py
  - backend/storage/db.py
  - backend/routers/models.py
  - src/components/composer/ModelConfigModal.tsx
  - src/lib/api.ts
  - src/lib/types.ts
created: 2026-07-13
---

## 背景

WB-132 的模型能力/成本用「按模型名启发式」给默认，已证实不可靠（DeepSeek v4-pro 支持推理却猜成
text+tools；GLM 各型号 tools/reasoning 是逐个定义的，名字推不出）。用户提供了权威文档：
- DeepSeek 定价/思考/工具（api-docs.deepseek.com）：现役 `deepseek-v4-flash`/`deepseek-v4-pro`，
  1M 上下文；**输入价分缓存命中/未命中（差 ~50×）**、人民币；思考是**参数开关**（v4-pro 支持）。
- 智谱 GLM（docs.bigmodel.cn model-overview）：每型号明标 **工具调用 ✓/✗、推理 ✓/✗**，视觉模型单列。

## 方案（用户已定）

1. **内置厂商准确默认表**：`provider_seed.MODEL_DEFAULTS`（key=model_id）按官方文档填 DeepSeek/智谱 的
   能力+价格+上下文+币种；未知模型回退名字启发式；用户手改仍最高优先。`_effective_meta` 优先级：
   用户覆盖(custom) > 内置准确默认(preset) > 名字启发式(default)。
2. **定价 schema 扩展**：`model_meta` 加 `input_cost_cached`(缓存命中输入价) + `currency`(¥/$)；ALTER 迁移。
3. **更新过时 seed 模型名**：DeepSeek → `deepseek-v4-flash`/`deepseek-v4-pro`；智谱 → 现役 GLM 子集。
   （运行时真值仍以「拉取最新」为准；seed 只作起点。）

## 验证

- tsc / py_compile 过；老库 ALTER 迁移不破坏。
- TestClient：v4-pro 默认 = 推理+工具+真价(3/0.025/6, CNY, source=preset)；GLM-4.6 = 工具+推理；
  未知模型仍走启发式；用户 PUT 覆盖(含 cached/currency)后 source=custom；reset 回 preset 而非 default。
- Playwright：DeepSeek 卡片显 v4-flash/pro + 真能力/价格；能力编辑器有缓存价+币种；徽标显示。

## 处理记录（2026-07-13）

- **后端**
  - `provider_seed.py`：DeepSeek seed → `deepseek-v4-flash`/`deepseek-v4-pro`；智谱 → `glm-4.6/4.5-air/4-flash/4.6v`；
    新增 `MODEL_DEFAULTS`（key=model_id）——DeepSeek 按官方定价页填能力+分档价(未命中/命中)+1M上下文+CNY；
    GLM 按 model-overview 填 tools/reasoning/vision + 上下文（价格文档未给→留空）。
  - `db.py`：`model_meta` 加 `input_cost_cached`/`currency` 列 + `_migrate_columns` 幂等 ALTER；CRUD 扩展。
  - `models.py`：`_effective_meta` 三级优先——用户覆盖(custom) > 内置准确默认(preset) > 名字启发式(default)；
    `ModelMetaIn`/PUT 收 input_cost_cached + currency。
- **前端**
  - `types.ts`/`api.ts`：ModelMeta + setModelMeta 加 input_cost_cached/currency；source 增 'preset'。
  - `ModelConfigModal`：能力编辑器加「缓存命中输入价」+「币种」两栏；徽标显 币种+价、preset 显「官方」小标。
- **验证**
  - tsc / vite build / py_compile 过。
  - 隔离 TestClient：v4-pro 默认=preset(text+tools+reasoning, 3/0.025/6 CNY, 1M) / GLM-4.6=工具+推理·4.6v含图片(价空) /
    未知模型回启发式 / PUT 覆盖(缓存价+币种)→custom / **reset 回 preset 而非 default** / 老库 ALTER 迁移+幂等 —— 全断言过。
  - 硬重启 :8000 后 Playwright 实测：DeepSeek 卡片显 v4-flash/pro + 徽标(caps + CNY1/2·CNY3/6 + 官方) +
    能力编辑器缓存价/币种从官方默认预填。全程只读未改用户数据。
- commit：（待用户确认时提交）

