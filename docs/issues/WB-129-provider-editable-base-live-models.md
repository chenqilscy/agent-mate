---
id: WB-129
title: 厂商渠道 base_url/请求路径可显示可编辑 + 在线拉取真实模型列表（治「预置值不准/模型名过时」）
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/storage/db.py
  - backend/routers/models.py
  - backend/agent/runtime.py
  - src/components/composer/ModelConfigModal.tsx
  - src/lib/api.ts
  - src/lib/types.ts
created: 2026-07-12
---

## 问题

WB-128 的厂商预置里，`base_url` 只读展示、模型名硬编码：
1. **base_url 不可改**：预置值对不上每个用户的实际配置（如用户 `.env` 是 `https://api.deepseek.com`
   而非 seed 的 `.../v1`；或走代理站/自建网关）。
2. **模型名会过时**：硬编码的模型列表迟早不准（铁律#1：不硬编码/不造假）。

## 建议修法

- **base_url + 请求路径（chat_path）可编辑、按 owner 持久化**：预置只作起点；有效值 = 用户覆盖 ∨ 预置默认。
  运行时（resolve_model_config）用有效值。留「恢复默认」（清覆盖）。
- **在线拉取模型**：厂商有 key 后，调其 OpenAI 兼容 `GET {base}/models` 实时列举真实模型
  （DeepSeek/Moonshot/Qwen/OpenAI 支持；个别不支持则如实提示「手动添加」）。拉到的模型一键加入。
  这样模型列表来自厂商实时数据，而非写死。

## 验证

- tsc / py_compile 过。
- TestClient + mock httpx：PATCH config 改 base/path → GET 反映有效值 + resolve 用有效值；
  fetch 端点按有效 base+key 打 `{base}/models` 并解析 `data[].id`；不支持时优雅报错。
- Playwright：改 DeepSeek base → 保存 → resolve 生效；点「拉取最新」列出真实模型并可添加；恢复默认。

## 处理记录（2026-07-12）

- **后端**
  - `db.py`：加 `provider_config`(owner,provider→base_url/chat_path 覆盖) 表 + `get/set_provider_config`（两者空=删行恢复默认）。
  - `models.py`：`_effective_base_path`(覆盖∨预置)；GET provider 出 `base_url`(有效)+`chat_path`+`default_base_url`+`default_chat_path`；
    加 `PATCH /providers/{id}/config`（空串=恢复默认）；加 `POST /providers/{id}/models/fetch`（async，用有效 base+key 打 `GET {base}/models`，解析 `data[].id`，不支持则如实报错）。
  - `runtime.py`：`resolve_model_config` 厂商分支改用有效 base/path（`get_provider_config` 覆盖优先）。
- **前端**
  - `types.ts` Provider 加 chat_path/default_base_url/default_chat_path；`api.ts` 加 setProviderConfig/fetchProviderModels。
  - `ModelConfigModal`：把只读 Base 行改成可编辑「接入地址」（Base URL + 请求路径 + 保存地址 + 覆盖时「恢复默认」）；
    模型区加「↻ 拉取最新」→ 列「厂商在线模型」，每个可「添加」（已有则标「已有」）。`app.css` 加 `.mc-cfg/.mc-modhd/.mc-fetched`。
- **验证**
  - tsc ✓；py_compile ✓。
  - 隔离 scratch DB + TestClient + mock httpx：改 base/path→GET 有效值 + resolve 覆盖优先；恢复默认回预置；
    fetch 打 `{base}/models` 解析 id / 厂商 404→ok:false 提示手动加 / 无 key→400 —— 全断言过。
  - 硬重启 :8000 后 Playwright 实测：DeepSeek 卡片 base 可编辑显示；**点「拉取最新」真打用户 .env 的 DeepSeek，
    拿回真实 `deepseek-v4-flash`/`deepseek-v4-pro`**（恰好印证「seed 模型名过时」——在线拉取即取到真值）。全程只读、未改用户配置。
- commit：（待用户确认时提交）

