---
id: WB-257
title: 桌面更新仍是占位 endpoint，缺少可配置发布服务、灰度回滚和真实入口
severity: P1
area: fullstack
status: open
origin: WB-239 R4
files:
  - src-tauri/src/lib.rs:1
  - src/platform/index.ts:1
  - src/components/settings/SettingsModal.tsx:1
  - server/main.py:1
created: 2026-07-21
parent: WB-239
---

## 问题

Tauri updater 插件和签名公钥已经接入，但配置仍指向 `REPLACE-WITH-YOUR-RELEASE-HOST`，App 没有实际检查
入口，Server 也没有不可变桌面 release、通道、稳定灰度分桶和失败遥测。当前只能手工替换占位地址后打包，
不能完成 R4 要求的升级、撤回和回滚演练。

## 触发场景

发布包含新 UI、sidecar 或 Tool contract 的桌面版本时，运营无法先投 beta/小比例 stable，也无法按设备得到稳定
版本；用户看不到检查结果和发布说明。错误版本上线后没有暂停/回滚目标和匿名失败计数，目录发布也无法判断
目标 App 是否已升级。

## 影响

P1：二进制能力不能安全运营，Skill/Tool 兼容门禁缺少真实客户端升级链，updater 脚手架不能满足 R4 退出条件。

## 建议修法

- Server 建立不可变桌面 release、平台产物、通道策略和更新检查遥测；只接受外部 CI 生成的签名与 URL；
- 更新端点按 channel、target、arch、current version 和稳定 device id 分桶，支持暂停、强制最低版本与回滚 release；
- Tauri 通过受控 Rust command 使用用户配置的 HTTPS endpoint，禁止任意非 HTTPS 生产地址并保留签名校验；
- App 设置页提供通道、自动检查、当前版本、检查/下载/安装失败状态和手工检查入口；Web 明确 unsupported；
- 增加发布 manifest 校验脚本/CI 示例，密钥和代码签名证书只从 CI secret 注入，不进入仓库或 Server。

## 验证

- 同一设备重复检查稳定命中同一灰度 release，不符合比例/平台/版本时返回 204；
- 暂停、回滚和最低版本策略返回确定版本并留下不含隐私正文的遥测；
- 非 HTTPS 自定义 endpoint 被桌面层拒绝，签名错误不能安装；Web 不显示假更新成功；
- App 可手动检查并显示真实状态，启动自动检查去重且失败不阻塞使用；
- Server/API、Rust、TypeScript、生产构建及本地签名 manifest 演练通过。
