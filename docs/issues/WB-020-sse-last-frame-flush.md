---
id: WB-020
title: SSE 末帧无空行不冲刷、末尾多字节可能丢失
severity: P2
area: frontend
status: open
origin: 🏚 既有实现
files:
  - src/lib/sse.ts:61
created: 2026-07-06
---

## 问题
`sse.ts` 只在遇到 `\n\n` 时切帧；`while` 结束后 `buffer` 里的残帧从不 dispatch。若服务端在最后一个 `data:` 后未补空行就关闭连接，`done` 帧丢失，bot 消息停留 `running`（与 WB-001 同后果）。另外循环结束未做一次无 `stream` 的 `decoder.decode()` flush，末尾多字节字符可能丢字符。

## 触发场景
后端最后一帧未以空行结尾（SSE 规范要求，但边界易违反）。

## 影响
边角：正常后端已按规范补空行；作为健壮性兜底。

## 建议修法
```ts
// 读循环结束后：
if (buffer.trim()) dispatchFrame(buffer, opts.onEvent)
// 并补最终 decoder.decode() flush
```

## 验证
构造末帧无空行的响应 → 仍能收到 done、消息 finalize；多字节末尾不丢字。
