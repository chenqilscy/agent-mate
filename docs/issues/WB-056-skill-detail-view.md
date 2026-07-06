---
id: WB-056
title: 技能详情页（渲染 SKILL.md + 预览/源码 + 去试试/启用/打开文件夹/卸载）
severity: P2
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/views/ExpertsView.tsx
  - src/components/skill/SkillDetail.tsx
created: 2026-07-07
---

## 问题

SkillHub 里点一个已安装技能应能打开「技能详情页」：展示该 skill 的 SKILL.md（预览/源码 </>
切换）、顶部「去试试」+ 启用开关 + ⋯（打开文件夹 / 卸载）。目前点技能卡无详情页。

依赖 [[WB-055]] 的后端读取端点（`GET /api/skills/{key}` 返回 SKILL.md 内容与元数据）。

## 触发场景

在「我安装的」或 SkillHub 网格点一个已安装技能 → 期望进入详情页看它到底是什么、能不能试/停用/卸载。

## 影响

P2：查看/管理已安装技能的入口缺失；纯前端展示（数据来自 WB-055 真实磁盘）。

## 建议修法

- 后端 `GET /api/skills/{key}` 返回 { frontmatter, markdown, references, meta }（见 WB-055）。
- 前端 `SkillDetail` 组件：头部标题+描述、去试试（summon 该技能开对话）、启用开关（调 toggle）、
  ⋯（打开文件夹 reveal / 卸载）；正文用既有 marked+DOMPurify+hljs 渲染 SKILL.md，
  提供「预览 👁 / 源码 </>」切换。样式复用既有 token，明暗双主题。
- 从 SkillHub 卡片 / 我安装的卡片点开进入。

## 验证

- 点已安装技能进详情，SKILL.md 正确渲染（预览/源码可切）；去试试进对话且该技能已挂 loadout；
  启用开关联动后端；打开文件夹弹出资源管理器；卸载后返回且列表移除。明暗双主题都看。

## 处理记录（2026-07-07）
- 前端：`components/skill/SkillDetail.tsx` —— 拉 `GET /api/skills/{key}`，头部标题/版本/描述 +
  去试试（summonSkills 挂技能开对话）+ 启用开关（.sw，调 toggle）+ ⋯（打开文件夹 reveal / 卸载）；
  正文用既有 `renderMarkdown`（marked+DOMPurify+hljs）渲染，预览 👁 / 源码 </> 切换；references 列出。
- 入口：SkillHub 网格/精选的已安装卡 + 我安装的卡点击进入（ExpertsView `detailKey` 占满 hub-body）。
- 样式复用既有 token，新增 `.skd-*`；`.skd-card`/viewtoggle 进 tokens 暗色覆盖。
- 验证：`npx tsc --noEmit` 过、`vite build` 过；渲染走与聊天同一 markdown 管线。live UI 待 :8000 重启后点一遍。
- commit：（本提交）
