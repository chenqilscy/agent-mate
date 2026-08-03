---
id: WB-383
title: SSO 密钥无版本轮换且就绪检查不能发现解密失败
severity: P2
area: backend
status: open
origin: 🆕 近期改动
files:
  - server/secret_crypto.py:13
  - server/sso_store.py:165
created: 2026-08-03
---

## 问题
密文只有 enc:v1 前缀且隐式依赖单个当前密钥；配置就绪只判断字段非空，不验证现有密文可解密。

## 触发场景
生产替换或丢失主密钥 → Provider 页面仍显示已配置/ready → 首次真实登录才报解密失败。

## 影响
P2。密钥轮换不可控，SSO 故障不能在发布前被 readiness 阻断。

## 建议修法
密文携带 key ID；支持 current + previous keyring 和原子重加密；启动/readiness 对启用 Provider 做解密探针。

## 验证
旧 key 密文可读并迁移到新 key；缺 key 或错误 key 使 readiness 明确失败；日志不含明文。
