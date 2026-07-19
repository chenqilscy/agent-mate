---
id: WB-200
title: 第三方 HTTP 请求日志会把 URL 路径中的连接凭据写入开发日志
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/main.py:1
  - backend/channels/telegram_api.py:27
created: 2026-07-20
---

## 问题

后端由 Uvicorn 启动后，`httpx` 的 INFO 请求日志会继承根日志配置。部分第三方 API 把凭据放在 URL 路径中，
因此连接检测或轮询时完整请求 URL 会进入 stderr/重定向日志，违反“密钥绝不输出”的铁律。

## 触发场景

启动已配置第三方渠道的本地后端 → 渠道管理器执行连接检测 → 开发日志出现完整请求 URL，
其中可能包含连接凭据。

## 影响

P1：本机日志、终端采集或问题报告可能意外带出凭据；即使日志不提交，也扩大了敏感信息暴露面。

## 建议修法

- 在应用日志初始化时把 `httpx` / `httpcore` 请求日志提升到 WARNING，业务层只记录脱敏后的渠道 ID/状态。
- 审查现有渠道日志，确保异常信息也不会拼接完整敏感 URL 或请求头。
- 清理本地开发日志中的历史敏感请求行，并在回归测试中捕获日志断言凭据不出现。

## 验证

- 使用测试凭据触发连接检测与一次失败请求，捕获 stdout/stderr，凭据全文命中为 0。
- 正常的“连接成功/失败”业务状态仍可观察，但只含渠道名称或脱敏 ID。
- 后端 `py_compile` 与渠道相关测试通过。

## 处理记录（2026-07-20）

- 应用导入第三方客户端前把 `httpx` / `httpcore` 日志级别提升为 `WARNING`，不再由 Uvicorn 根 INFO 日志记录完整请求 URL。
- 硬重启本地后端并清空旧开发日志；健康检查正常。
- 捕获日志回归：两类 logger 级别均为 30，测试 URL 凭据命中 `0`；当前 live stderr 的 `HTTP Request:` 行数为 `0`。
- `backend/main.py` 通过 `py_compile`。

状态：`fixed`（本次提交，见 Git 历史）。
