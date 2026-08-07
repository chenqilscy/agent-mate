---
id: WB-433
title: 设备身份与 Run 租约事件可靠传输协议
severity: P1
area: backend
status: open
origin: 🆕 近期改动
files:
  - server/routers/relay.py:1
  - server/db.py:180
  - backend/agent/runtime.py:1
  - backend/agent/scheduler.py:1
created: 2026-08-08
---

## 问题

父项：[WB-431](archive/2026/WB-400-499.md#wb-431)，依赖 WB-432 的 Run schema。现有 relay 只支持外部事件租约，没有 Local Agent 设备注册、Run fencing、顺序事件 WAL/ACK、取消和断线续传的完整协议。

## 触发场景

Local Agent 执行中断网、崩溃或发生双 worker 竞争时，Server 不能以统一协议确认哪一个执行者有效，也不能证明事件不丢失、不重复生效。

## 影响

P1：没有可靠执行通道就不能把 Run 权威迁入 Server，也不能安全支持后台或 headless Local Agent。

## 建议修法

- 建立 device registration、密钥 challenge、capability report、heartbeat 和撤销。
- 建立 `lease_id/lease_epoch`、续租、超时、fencing、取消和 checkpoint 语义。
- 定义 `event_id + run_id + lease_epoch + seq`、本地 WAL、Server 去重和连续 ACK 高水位。
- 支持 seq gap 补传、容量门禁、ask_user 往返和协议版本兼容。

## 验证

- 覆盖断网重连、重复发送、Server/Agent 重启、租约过期和双 worker 竞争。
- 没有重复工具副作用；Server 事件序列无缺口，Local WAL 只在 ACK 后清理。
- 撤销设备和旧 epoch 不能领取或提交新的执行结果。
