---
id: WB-206
title: 添加技能只有搜索聚焦，缺少上传导入与创建流程
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:735
  - src/components/skill/AddSkillControl.tsx:1
  - backend/routers/skills.py:98
  - backend/agent/skills_store.py:198
  - backend/agent/skills.py:250
  - backend/storage/db.py:570
created: 2026-07-20
---

## 问题

技能页右上角“＋ 添加技能”目前只把焦点移到搜索框。后端只有 SkillHub 搜索/安装接口，没有上传本地 `SKILL.md`、导入技能包或引导创建技能的能力，因此按钮名称表达的完整功能并未实现。

## 触发场景

进入“技能”页点击“＋ 添加技能”：页面仅聚焦搜索框，无法像参考的腾讯 WorkBuddy 一样选择“上传技能 / 创建技能”，也无法把本地技能包加入真实的已安装技能目录。

## 影响

P1：用户只能安装 SkillHub 已存在的技能，不能迁入本地技能或从应用内启动技能创建流程；核心扩展入口与界面承诺不一致。

## 建议修法

- 保留顶栏现有真实 SkillHub 搜索；将“添加技能”改为两项菜单：“上传技能”打开导入弹窗；“创建技能”挂载内置 `skill-creator-guide` 并进入新任务。
- 后端新增本地技能导入端点，支持单个 `.md`、包含唯一 `SKILL.md` 的 `.zip` 和浏览器文件夹选择；校验 YAML frontmatter 的 `name`/`description`、路径穿越、压缩包大小/文件数及同名冲突，成功后原子落盘到 `SKILLS_DIR`。
- 导入成功后强制刷新 `skillStore`，进入“我安装的”并可打开详情、挂载进会话。
- 沿用现有 token 与 `.np-*` 弹窗骨架，检查明暗主题和窄宽布局。

## 验证

- 菜单“上传技能 / 创建技能”均有真实行为，且不重复顶栏已有的查找入口；点击外部与 Esc 可关闭。
- `.md`、`.zip`、文件夹三种导入成功后出现在“我安装的”，内容来自真实磁盘；缺失/多个 `SKILL.md`、非法路径、超限及重复 slug 均明确失败且不留下半成品。
- “创建技能”进入 composer，挂载 `skill-creator-guide` 并预填创建提示；生成完成后调用受约束工具真实安装。
- 后端回归测试、Python 编译、`npx tsc --noEmit`、生产构建通过；浏览器明暗主题和窄宽窗口通过。

## 处理记录（2026-07-20）

- 改动：技能页“＋ 添加技能”新增“上传技能 / 创建技能”菜单，查找继续由顶栏搜索框承担，避免入口重复；上传弹窗支持拖拽/选择 `.md`、`.zip` 和本地文件夹，成功后刷新真实已安装列表。后端新增流式文件导入与文件夹导入接口，限制 20MB/256 文件/512KB 清单，校验唯一 `SKILL.md`、UTF-8、frontmatter、路径穿越、重复路径、符号链接、加密包和 slug 冲突，并通过同卷临时目录原子落盘。
- 创建：没有照搬本机不存在的 `skill-creator` 假身份，改接真实内置 `skill-creator-guide`；新增 `create_local_skill` 工具和旧库条件迁移，助手确认字段后会生成规范 `SKILL.md` 并直接安装到 `SKILLS_DIR`。
- 验证：Python 编译通过；新增导入/创建及旧库迁移回归，完整 regression 7/7 通过；`npx tsc --noEmit`、`npx vite build`、`git diff --check` 通过。硬重启 `:8000` 后真机验证 `.md` 与文件夹导入→列表→详情→清理全通；浏览器实测两项菜单、Esc/外部关闭、无效文件错误、真实导入、创建入口 loadout 和预填提示；1280/960/860px、明暗主题无横向溢出。
- commit：本提交（WB-206）。
