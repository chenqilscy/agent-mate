---
id: WB-037
title: 编辑自动化时「解绑工作空间」静默失败（UI 已清空 + 提示已保存，实际仍绑定）
severity: P3
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/views/AutomationView.tsx
  - backend/routers/automations.py:122
created: 2026-07-06
---

## 问题

WB-036 的全屏编辑器支持给自动化**设置/切换**工作空间，但**解绑**（清空到「不绑定」）在编辑
既有自动化时**静默失败**：

- 前端编辑器点工作空间 chip 上的「×」或选「不绑定（默认工作区）」→ 本地 `projectId` 置 `null`，
  UI 立刻显示已清空；点「保存」→ store `update(id, {..., project_id: null})` → `PATCH`。
- 后端 `update_automation`（[`automations.py:122`](../../backend/routers/automations.py#L122)）用
  `body.model_dump(exclude_none=True)` 落库，`project_id=None` 被 `exclude_none` **丢弃**；
  即便不丢，`db.update_automation` 的 `_AUTOMATION_FIELDS` 循环也会 `if v is None: continue`
  跳过——两道都把「清空」吞掉。
- 结果：`PATCH {"project_id": null}` 回来的 automation **仍带原 project_id**；store 用返回值刷新，
  于是保存后（或重开编辑器）工作空间**又回来了**。但用户已看到 chip 被移除 + toast「已保存」，
  以为解绑成功——**假反馈**。

这是 WB-036 一期**有意的**限制（当时只做设置/切换，见 WB-036「建议修法/处理记录」），
但「UI 清空 + 提示已保存却没真正生效」这层**误导反馈**当时未单列，本 issue 补登记以便跟踪。

已用后端核实：`POST` 建一条绑定 `project_id` 的自动化 → `PATCH {"project_id": null}` →
回读 `project_id` **未变**（仍是原项目）。

## 触发场景

1. 有一条绑定了工作空间的自动化，进「⋯ → 编辑」。
2. 点工作空间 chip 的「×」（或选「不绑定」）→ chip 消失。
3. 点「保存」→ toast「已保存」，编辑器关闭。
4. 重新进「编辑」→ 工作空间**又在**（解绑没生效）。

## 影响

P3：仅「解绑」这一条路径失真；设置/切换工作空间正常、运行照常。无数据丢失或安全问题。
但假反馈会让用户以为已解绑，属 铁律 #1（不模拟/不给假反馈）范畴的小缺口。

## 建议修法

让 `PATCH` 能表达「显式清空 project_id」，并保证前端只在真落库后才提示成功：

- 后端：给 update 路由的 `project_id` 一个可区分「未提供」与「显式置空」的表达。可选：
  - 用哨兵/单独字段（如 body 里带 `clear_project: bool`），或
  - update 路由不对 `project_id` 走 `exclude_none`，显式传 `project_id`（含 `None`）给
    `db.update_automation`；并让 `_AUTOMATION_FIELDS` 的循环对 `project_id` 允许写 `NULL`
    （把「跳过 None」的规则改为仅对确实不该清空的列生效）。注意别把「未提供 project_id」
    误当成「清空」——需要 body 层面区分 `unset` 与 `null`（Pydantic `model_fields_set`）。
- 前端：解绑走上述显式清空通道；`update` 失败或未变更时不弹「已保存」。

（若决定**不做**解绑，则改为在 UI 上禁用/移除既有自动化的「×/不绑定」，避免给出无效操作，
同样消除假反馈。二选一即可。）

## 验证

- 后端：`PATCH` 显式清空 → 回读 `project_id` 为 `null`；「未提供 project_id」的 `PATCH` 不误清空。
- 前端：编辑既有绑定自动化 → 解绑 → 保存 → 重开编辑器工作空间确为空；新建时不绑定仍正常。
- 回归：设置/切换工作空间不受影响；`model`/其它字段更新不被牵连。

## 处理记录（2026-07-06）

- 后端：update 路由改用 `body.model_dump(exclude_unset=True)`——只把客户端**实际传了**的字段落库，于是显式
  `null` 能清空、未传字段保持不动；`db.update_automation` 新增 `_AUTOMATION_NULLABLE={project_id, model}`，
  仅这两列允许写 `NULL`（其余列仍跳过 None）。归属校验保留（设工作空间→非本人 404，清空跳过检查）。
- 前端：编辑器解绑（chip「×」/「不绑定」）本就把 `projectId` 置 null 并随保存发出，配合后端即真解绑。
- 验证：后端 curl——建一条绑定+带模型的自动化 → `PATCH {project_id:null}` 回读 project_id=None、model 不变；
  再 `PATCH {model:null}` 两者皆 None；只传 name 的 `PATCH` 不误清空 model；坏 project_id 仍 404。
- commit：（尚未提交）
