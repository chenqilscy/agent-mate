---
id: WB-250
title: Console Skill 管理仍是可变 CRUD，缺少测试审核灰度撤回和运行指标闭环
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - console/src/SkillsPage.tsx:44
  - console/src/SkillEditor.tsx:67
  - server/routers/catalog.py:392
created: 2026-07-21
---

## 问题

Console 当前直接创建或 PATCH 可变目录项，保存后即成为下行定义；没有 draft、真实 Test Run、作者/审核者
分离、权限 diff、灰度分桶、兼容覆盖、撤回/回滚和版本运行指标。运营无法在发布前证明 Skill 能在目标
App 版本上真实执行，也不能安全地分批放量。

## 触发场景

- 运营修改 Skill 工具后直接保存，所有下一次 pull 的客户端立即看到新定义。
- 发布失败只能再次编辑当前行，没有不可变上一版本可回滚。
- 无法查看不同 release 的安装成功率、运行成功率、工具错误和回滚率。

## 影响

P1：Console 具备管理页面但尚未形成生产能力发布系统，扩大运营规模后变更风险不可控。

## 建议修法

- Skill 编辑产生 draft release；提供真实客户端 Test Run 和 trace/产物结果。
- 状态机覆盖 draft、testing、approved、rolling_out、published、withdrawn、superseded。
- 发布配置最低 App/工具契约、组织/通道/比例和生效时间；稳定设备分桶避免版本抖动。
- 展示内容/工具/权限 diff、审核与发布审计、兼容覆盖及非敏感运行指标。

## 验证

- 未发布 draft 不进入普通 App 下行；Test Run 失败不能发布。
- 发布、灰度、暂停、撤回和回滚均有审计记录并返回确定的客户端版本。
- Console 能查看 release 历史、权限 diff 和按版本聚合的运行结果。

## 处理记录

- 2026-07-21：Server 新增不可变 `skill_releases`、`skill_release_audit` 与聚合指标表；状态机覆盖
  draft/testing/approved/rolling_out/published/withdrawn/superseded，普通 `APP_SKILLS` CRUD 不再允许
  直接修改纳管定义或发布状态。
- 客户端 Test Run 以真实 Run ID、App/工具契约、trace/产物引用和结果回传；失败结果不能审核，作者
  不能审核自己的 release。发布支持通道、比例与生效时间，按账号稳定分桶；暂停回到 last-known-good，
  撤回显式下发 tombstone，回滚会从历史内容生成新的不可变版本。
- Console 编辑器改为“保存草稿”，发布治理页展示版本状态、内容/工具/权限 diff、测试、审核、灰度、
  暂停、撤回、回滚、审计与安装/运行指标。App 安装与 runtime 按 release best-effort 上报非敏感聚合
  事件，不上传 prompt、文件、工具参数或凭据。
- 回归覆盖未发布草稿不可见、失败测试阻断、自审阻断、全量发布、稳定灰度、暂停、tombstone、回滚、
  审计与指标；Server/Backend Skill 回归和 Console 类型检查通过。
