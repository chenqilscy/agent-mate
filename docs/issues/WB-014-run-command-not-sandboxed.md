---
id: WB-014
title: run_command 非真沙箱（shell=True，仅钉 cwd）
severity: P2
area: backend
status: fixed
origin: 🏚 既有实现
files:
  - backend/agent/tools.py:151
  - backend/config.py
created: 2026-07-06
---

## 问题
`run_command`（`tools.py:151`）用 `shell=True` 执行任意 shell 命令，cwd 被钉在 workspace，但命令本身可 `cd ..`、读写任意路径、联网、`rm -rf`、装包等。`current_root()` 仅约束工作目录，不构成沙箱。工具描述与系统提示词却宣称「沙箱内/有超时」，具误导性。

## 触发场景
模型（可被 refs 文件正文或 `web_fetch` 抓回的网页做提示注入诱导）发起 `run_command`。若 `HOST` 改成 `0.0.0.0`（config 支持）且无鉴权 → 等于对局域网开放 RCE。

## 影响
本地单用户设计如此、风险可接受；但「沙箱」承诺不成立，且网络暴露 + 提示注入下是真实风险。

## 建议修法
- 短期：把工具描述/系统提示改为「非沙箱、高风险」；坚持只绑 `127.0.0.1`（文档强约束）。
- 中期：命令白名单 / 危险命令需显式 `ask_user` 授权；考虑 `shell=False` + 参数化。

## 验证
描述已如实标注；`HOST` 默认 127.0.0.1；（若实现白名单）越权命令被拦并要求确认。

## 处理记录（2026-07-06）
- 改动：run_command 工具描述与 tools.py 模块文档如实标注「非真沙箱，命令以后端权限执行、可访问任意路径与网络」；坚持 HOST 默认 127.0.0.1（config 未改）。（backend/agent/tools.py）
- 验证：描述已更新如实标注；`settings.HOST` 默认 127.0.0.1。中期白名单/授权留待 M4。
