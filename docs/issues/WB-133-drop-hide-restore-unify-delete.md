---
id: WB-133
title: 去掉厂商模型「隐藏/恢复」机制，统一为「删除」
severity: P3
area: frontend
status: fixed
origin: 既有实现
files:
  - src/components/composer/ModelConfigModal.tsx
  - src/lib/api.ts
created: 2026-07-13
---

## 问题

WB-128 给厂商模型分了两套动作：预置模型「隐藏/恢复」（灰掉可还原），自加模型「删除」。
用户觉得这个两层机制多余，只想要一个统一的「删除」。

## 方案（用户已定：统一改成可删除）

- 每个厂商模型都只留一个「删除」按钮；不再有隐藏/恢复、不再有灰掉的行。
- 删预置 = 从列表与 picker 移除（复用后端既有「hidden=1」标记，仅内部记「已删」，UI 不再展示它）；
  删自加 = 删行。要用回来 → 「拉取最新」或手填加回（`add_provider_model` 命中同名会自动取消 hidden）。
- 后端无需新端点：`POST /providers/{id}/models/hide {model_id, hidden:true}` 已能对预置/自加统一"移除"；
  前端 api 方法更名为 `deleteProviderModel` 让语义清晰。管理列表前端过滤掉 hidden 项。

## 验证

- tsc / build 过。
- Playwright：厂商模型行只剩「删除」；删预置(如 deepseek-chat)→ 列表与 picker 都不再出现；
  「拉取最新」重新添加同名 → 回来；无灰行、无恢复按钮。

## 处理记录（2026-07-13）

- **前端**（后端无改动，复用既有端点）
  - `api.ts`：`hideProviderModel` → 更名 `deleteProviderModel(pid, mid)`（POST /providers/{id}/models/hide, hidden:true）。
  - `ModelConfigModal.tsx`：`toggleModel` → `deleteModel`；模型列表 `p.models.filter(m => !m.hidden)`（删掉/隐藏的不再显示）；
    每行动作从「预置=隐藏/恢复 · 自加=删除」的二选一，收敛为**统一一个「删除」**；去掉 `.off` 灰行。
- **验证**
  - tsc ✓ / vite build ✓。
  - Playwright 实测：DeepSeek 4 个模型行均只剩 [能力, 删除]，全页无「隐藏/恢复」字样、无灰行；
    OpenAI（无 key，不碰用户 DeepSeek 配置）删 `gpt-4o` → 列表移除 → 手填 `gpt-4o` 加回 → 复现，端到端通。
- commit：（待用户确认时提交）

