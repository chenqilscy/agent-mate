---
id: WB-089
title: 多助理 S3+S4 收尾 —— 移除兼容层 + 端到端验证 + 关闭 epic
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/channels/manager.py
  - backend/routers/channels.py
  - src/lib/api.ts
  - docs/issues/WB-086-multi-assistant-multi-channel-epic.md
created: 2026-07-08
---

## 问题

WB-088（S2）已把前端切到 `/api/assistants*`，WB-087 里为过渡保留的 `/channels/telegram*`
兼容层 + 前端旧方法已无人调用（grep 确认仅 api.ts 定义处）。本片移除死代码并做 epic 级验证收口。
（S3 渠道路由 UI 已并入 S2；此片承接 S3 的路由验证 + S4 的清理/收口。）

## 建议修法

- `channels/manager.py`：删 `compat_status/compat_config/compat_unbind/compat_say` + `_primary_*` 辅助。
- `routers/channels.py`：删旧 `GET/POST/PATCH /channels/telegram*` 兼容端点（保留 `/channels/types` +
  `/assistants*`）。
- `lib/api.ts`：删 `getTelegramChannel/telegramSay/patchTelegramConfig/telegramUnbind` + `TelegramChannel` 类型。
- 关闭 epic WB-086（S1 WB-087 / S2 WB-088 / 本片 WB-089 收口）。

## 验证

- `py_compile` / `tsc` / `vite build` 通过；grep 确认无残留引用。
- 重启 :8000：`/assistants` 正常、迁移的单助理 @CkyBuddyBot 仍 running/connected；旧 `/channels/telegram`
  已 404（预期）。
- 多 bot 路由：离线（WB-087 已证同 chat_id 跨渠道独立会话 + poller 协调）+ 单 bot 真机存活；第二个真实
  bot 的实机路由需用户再建一个 bot（机制已证，凭据待用户）。

## 处理记录（2026-07-08）

- 改动：删 `manager.py` 的 `compat_*` + `_primary_*`；删 `routers/channels.py` 旧 `/channels/telegram*`
  兼容端点（保留 `/channels/types` + `/assistants*`）；删 `lib/api.ts` 的 `getTelegramChannel/telegramSay/
  patchTelegramConfig/telegramUnbind` + `TelegramChannel` 类型。
- 验证：grep 确认无残留引用；`py_compile`/`tsc`/`vite build` 通过；重启 :8000 后 `/assistants` 正常、
  迁移助理「小助」+ telegram 渠道 `running=True bound=8617683065`（@CkyBuddyBot 存活）、`/channels/types`
  正确（仅 telegram available）、旧 `/channels/telegram` 返回 404（预期）。
- epic WB-086 收口：S1=WB-087、S2(+S3 前端)=WB-088、S3 路由验证+S4 清理=本片 WB-089；原 WB-090 并入本片。
- commit：（尚未提交）
