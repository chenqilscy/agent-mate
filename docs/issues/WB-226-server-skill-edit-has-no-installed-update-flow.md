---
id: WB-226
title: Server 技能编辑后已安装副本没有版本与更新闭环
severity: P1
area: fullstack
status: fixed
origin: 技能功能复查
files:
  - server/web/console.html:1998
  - backend/routers/skills.py:71
  - backend/agent/skills_store.py:239
  - backend/agent/skills_store.py:394
  - src/components/skill/SkillDetail.tsx:63
created: 2026-07-21
---

## 问题

Console 可以修改技能指令和随包文件，但目录定义没有可运营的版本字段，App 也不会比较 Server 定义与本机安装快照。
已安装技能继续运行旧 `SKILL.md` 和旧文件；详情页只显示“已安装”，没有“有更新”或升级入口。
再次调用安装接口会因同 slug 目录已存在而返回 409，只有手工卸载再安装才能获得新内容。

## 触发场景

先在 App 安装一个 Server 目录技能，再到 Console 修改其技能指令或 reference 文件并保存。App 完成 pull 后打开详情、执行技能，
仍使用安装时的旧快照；没有更新提示，直接重装也失败。

## 影响

P1：运营端“编辑技能”对已安装用户不生效，安全修订、提示词修正和参考文件更新都无法可靠分发，形成不可见的版本分叉。

## 建议修法

- 为 Server 目录技能增加单调版本或内容摘要，并把版本写入生成的 `SKILL.md` 与 App 安装元数据。
- App pull 后比较已安装版本/摘要，展示“有更新”；提供显式升级操作。
- 升级采用 staging + 原子替换，保留启停状态；失败时原版本不变。是否自动升级需明确策略，默认由用户确认。
- 与 WB-207 的本机技能编辑闭环划清边界：Server 管理技能走发布升级，本机自定义技能走本地编辑。

## 验证

- 安装 v1 后在 Console 发布 v2，App 能识别更新并展示版本差异。
- 点击升级后指令和所有文件原子切换为 v2，启停状态不丢；失败回滚 v1。
- 同版本重复升级幂等，旧 App 遇到新版本字段仍可兼容运行。

## 处理记录（2026-07-21）

- 改动：复用 Server 目录项递增 version，下行持久化到 App catalog 与安装 SKILL.md；详情比较本机/目录版本并展示升级入口；升级使用 staging、目录交换与失败恢复，保留 `.disabled` 状态。
- 验证：真实完成 Console v1 发布→App 安装→Console v2→App 显示“升级到 v2”→升级后正文切换 v2；自动化覆盖文件替换、版本消除与停用状态保留。
- commit：本次 WB-207/WB-224～229 合并提交。
