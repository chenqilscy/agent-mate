---
id: WB-274
title: 旧模型选择解析会截断含冒号的真实模型 ID
severity: P3
area: backend
status: fixed
origin: 🏚 迁移遗留
files:
  - backend/agent/runtime.py:177
created: 2026-07-22
---

## 问题
旧 `Display:real-id` 兼容分支使用 `rsplit(':', 1)`。真实 ID 若为 `vendor/model:free`，会错误解析为 `free`；带显示名的 `Display:vendor/model:free` 也同样截断。

## 触发场景
旧客户端或存量设置传入 `vendor/model:free`，运行时向模型供应商发送 `model=free`。

## 影响
P3。仅影响旧兼容/直接输入路径，新 `@provider:model` 与数据库自定义模型不受影响。

## 建议修法
把旧格式解析收敛为独立函数：有显示标签时只切第一个冒号；冒号前已含供应商路径 `/` 时视为裸真实 ID，整体保留。

## 验证
- `Display:vendor/model:free` → `vendor/model:free`。
- `vendor/model:free` → `vendor/model:free`。
- `Display:real-id` → `real-id`。
- 后端编译和回归测试通过。

## 处理记录（2026-07-22）
- 改动：新增 `parse_legacy_model_id` 并接入 `resolve_model_config`；旧显示标签只切第一个冒号，冒号前已有供应商路径的裸 ID 整体保留。
- 验证：`runtime.py` 与测试文件编译通过；`test_legacy_model_id` 3 项通过，覆盖带标签含冒号、裸供应商路径、普通非旧格式。
- commit：本提交。
