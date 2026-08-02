---
id: WB-360
title: 完整 V1 质量门禁未自动执行且测试依赖在线模型下载
severity: P1
area: misc
status: open
origin: 既有实现
files:
  - scripts/validate-v1-rc.ps1:60
  - backend/agent/mem_embed.py:37
created: 2026-08-03
---

## 问题

仓库已有完整验证脚本，但没有提交/PR CI 工作流；回归运行还会尝试下载 HuggingFace embedding 模型，冷环境不可重复。

## 触发场景

只运行定向测试即可提交破坏完整门禁的变更；离线或限网 CI 会在模型下载处变慢或失败。

## 影响

P1。质量规则存在但未被自动执行。

## 建议修法

增加 Windows CI 调用完整 V1 门禁；测试环境默认禁用模型下载并使用显式 fake/mocked embedding，真实模型测试单独标记。

## 验证

- CI 配置覆盖 App、Console、Backend、Server、integration 和 Python compile；
- 回归在无网络环境不下载模型；
- 本机完整门禁通过。
