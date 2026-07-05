---
id: WB-022
title: CONTEXT_WINDOW=0 触发 usage 除零
severity: P2
area: backend
status: fixed
origin: 🏚 既有实现
files:
  - backend/agent/runtime.py:129
  - backend/config.py:34
created: 2026-07-06
---

## 问题
usage 计算 `pct = used / settings.CONTEXT_WINDOW * 100`（`runtime.py:129`）。若 env 把 `CONTEXT_WINDOW` 配成 0，流末尾 `ZeroDivisionError`。

## 触发场景
误配 `CONTEXT_WINDOW=0`。

## 影响
配置健壮性，低危。

## 建议修法
下限保护：`max(1, settings.CONTEXT_WINDOW)`，或在 config 校验时拒绝 ≤0。

## 验证
配 `CONTEXT_WINDOW=0` 启动并发消息 → 不崩，pct 合理降级。

## 处理记录（2026-07-06）
- 改动：`CONTEXT_WINDOW = max(1, int(os.getenv(...)))` 下限保护。（backend/config.py）
- 验证：verify_backend.py「CONTEXT_WINDOW clamped 0->1」PASS；usage 计算不再除零。
