---
id: WB-386
title: 模型配置缺少组织策略预算健康检查和受控故障转移
severity: P2
area: fullstack
status: open
origin: 既有实现
files:
  - backend/routers/models.py:238
  - backend/storage/db.py:1
created: 2026-08-03
---

## 问题
模型凭据和用量按 owner 管理，但没有组织允许列表、周期预算、Provider 健康状态、密钥轮换提示或受控 fallback；自定义 base URL 也没有统一治理边界。

## 触发场景
多人/团队使用不同自定义模型 → 成本超额、Provider 故障或目标地址不合规 → 系统只能逐用户人工排查和切换。

## 影响
P2。模型规模化运营、成本控制和安全治理不足。

## 建议修法
增加用户级策略和可继承的 Server 组织策略：模型 allowlist、日/月软硬预算、Provider health、明确 fallback 链、凭据更新时间；限制自定义地址为合法 HTTP(S) 且阻止共享后端访问本地/保留地址。

## 验证
策略在模型解析和调用前执行；预算边界与 fallback 有回归测试；健康检查不泄漏 key；local-first 单用户默认行为兼容。
