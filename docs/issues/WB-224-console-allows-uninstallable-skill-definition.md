---
id: WB-224
title: Console 允许保存无法被 App 查看和安装的不完整技能定义
severity: P1
area: fullstack
status: fixed
origin: 技能功能复查
files:
  - server/web/console.html:2007
  - server/routers/catalog.py:72
  - backend/routers/skills.py:62
  - backend/agent/skills_store.py:394
  - backend/storage/db.py:1702
created: 2026-07-21
---

## 问题

Console 新增/编辑技能只校验 slug 与名称，Server 的 `APP_SKILLS` 校验和 App 下行入库也接受空简介、空技能指令；
但 App 的目录详情要求存在 instructions，真实安装又要求 name、description、instructions 三项齐全。
因此运营端能够成功保存并下发一个 App 无法查看或安装的技能。

## 触发场景

打开 `/catalog/skills` → 目录管理 → 新增技能，只填写合法 slug 和名称后保存。Console 提示成功且列表出现该技能；
App 请求目录详情时得到 404，安装链路则会拒绝“不完整定义”。2026-07-21 使用临时 slug
`audit-incomplete-skill` 浏览器实测复现，随后已删除测试数据。

## 影响

P1：发布端与消费端契约冲突，会把“保存成功”变成客户端不可用内容，且问题可能在下行后才暴露。

## 建议修法

- 抽出统一的目录技能定义契约；至少要求 slug、name、description、instructions，并统一长度限制。
- Console 在字段旁显示必填标识和就地错误；Server 作为最终权威再次校验，App 保留防御性校验。
- 下行遇到不完整定义时不能静默入库，应拒绝该条并留下可观察的同步错误。

## 验证

- Console 与 Server 均拒绝缺少 name、description 或 instructions 的新增/编辑请求，且错误落到具体字段。
- 合法技能仍能下行、查看详情并安装；Server、App 契约测试覆盖同一组边界值。

## 处理记录（2026-07-21）

- 改动：Console、Server 与 App 下行统一要求 name、description、instructions，统一长度限制；Console 标明必填并就地拦截，Server 保持最终权威，旧 Server 的不完整定义由 App 跳过并计数。
- 验证：真实页面只填 slug/名称时无法保存；Server 契约和 App 下行回归覆盖三项缺失、长度与合法定义安装，全部通过。
- commit：本次 WB-207/WB-224～229 合并提交。
