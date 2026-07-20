---
id: WB-204
title: 技能身份、目录下发与分类筛选缺少自动回归门禁
severity: P2
area: test
status: fixed
origin: 本轮收敛审查
files:
  - backend/tests/
  - package.json
created: 2026-07-20
---

## 问题

技能子系统同时横跨 App DB、Hub 目录、项目/助理持久化与前端分类渲染。现有验证以手工脚本和真 LLM
功能测试为主，没有一条可重复运行的离线门禁覆盖“展示名迁移为 slug、Hub 下发覆盖、分类来自真实目录”这三项关键契约。
这使旧展示名、无分类三元组或静态 SkillHub 假数据以后可能悄悄复活。

## 建议修法

增加不依赖外部 LLM/SkillHub 的回归测试，覆盖存量迁移幂等性、目录下发与分类数据形状；在项目脚本中提供
一个稳定入口，并与 TypeScript 类型检查、生产构建组成可执行的回归门禁。

## 验证

- 回归测试可在离线环境重复运行且通过；
- `npx tsc --noEmit` 与 `npx vite build` 通过；
- 故意回写展示名或无 category 数据时测试会失败。

## 处理记录（2026-07-20）

- 新增离线回归：存量展示名→slug、幂等迁移、Hub 同 slug 覆盖、非法 slug 跳过、推荐卡 category 契约。
- 新增 `npm run test:regression`，串联 Python 回归与 TypeScript 类型检查。
- 更新真机功能测试为 slug 输入，并让新测试账号显式选择 backend `.env` 测试模型，避免“未设置默认模型”误报。
- 验证：离线 2/2、真 LLM 技能/连接器 15/15、生产构建通过。

状态改为 `fixed`。
