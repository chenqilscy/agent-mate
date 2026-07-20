---
id: WB-219
title: Console 技能编辑缺少弹窗与真实文件管理
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - server/web/console.html:1922
  - server/routers/catalog.py:58
  - backend/storage/db.py:337
  - backend/agent/skills_store.py:394
created: 2026-07-21
---

## 问题

Console 的技能目录管理把新增表单常驻在列表顶部，点击“编辑”只把数据回填到顶部并滚动页面，
没有弹窗或独立详情边界。更关键的是，`APP_SKILLS` 目前只保存 slug、描述、指令和工具绑定，
没有技能文件字段，所以管理端没有也无法提供文件管理入口；App 安装目录技能时也只生成一个
`SKILL.md`，无法携带 references、脚本或模板等配套文件。

## 触发场景

打开 `/catalog/skills` → 目录管理 → 编辑任意技能，需要跳到页面顶部修改；想查看或维护该技能的
`SKILL.md` 与引用文件时没有入口。即使运营定义需要 `references/guide.md`，当前下行和安装都会丢失。

## 影响

P1：Server 技能库只能维护一段指令而不是完整技能包，复杂技能所需参考资料无法随定义分发；
编辑体验也与 Console 已有弹窗模式不一致。

## 建议修法

- 将新增/编辑技能改为沿用 Console 既有弹窗骨架，提供“基本信息 / 文件”两个页签。
- `SKILL.md` 由基本信息与技能指令生成并在文件页明确展示；允许新增、编辑、删除安全的相对路径文本文件。
- Server 校验文件数量、总体积、重复路径、绝对路径与 `..` 路径穿越，禁止覆盖生成的 `SKILL.md` 和运行时保留文件。
- App 的 `catalog_skills` 增加 files JSON，下行保存；安装目录技能时把这些文件真实写入本机技能目录。

## 验证

- Console 点“新增技能”或“编辑”打开弹窗；基本信息与文件页签可切换，文件 CRUD 后保存并重新打开可恢复。
- 非法/重复/保留路径被 Server 拒绝；合法嵌套文本文件可保存。
- Server 下行后 App DB 保留 files；安装目录技能后 `SKILL.md` 与附加文件真实落盘、内容一致。
- Console 脚本语法、Python 编译、Server/Backend 回归、TypeScript 类型检查与浏览器真实页面验收通过。

## 处理记录（2026-07-21）

- 改动：Console 技能目录管理改为列表 + 新增/编辑弹窗，弹窗含“基本信息 / 文件”页签；每条技能增加独立“文件”按钮，`SKILL.md` 明确由元数据与指令生成，附加文本文件支持新增、编辑、删除。Server 校验安全相对路径、重复/保留文件、128 文件与 1MB 上限。App `catalog_skills` 前向增加 `files` JSON，下行保留，安装目录技能时与生成的 `SKILL.md` 一起真实落盘。
- 验证：Console 脚本语法、4 个 Python 文件编译、`npx tsc --noEmit`、Server 5/5 与 Backend 7/7 定向回归通过；真实 `:8100` API 保存/读回 `references/guide.md`，`../escape.txt` 返回 400，临时技能已删除；`8101` 旧库补列成功。浏览器真实打开 Web Access 文件弹窗，新增临时文件后计数 1→2、取消无写入，布局与控制台错误检查通过。
- commit：本次 WB-219 提交（见 Git 历史）。
