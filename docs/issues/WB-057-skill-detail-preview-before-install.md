---
id: WB-057
title: 技能详情应支持"安装前预览"（从 SkillHub 拉取，而非仅本地磁盘）
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/skills_store.py
  - backend/routers/skills.py
  - src/components/skill/SkillDetail.tsx
  - src/views/ExpertsView.tsx
created: 2026-07-07
---

## 问题

[[WB-056]] 的技能详情页只读本地磁盘：`GET /api/skills/{key}` 走 `~/.workbuddy/skills/<key>`，
所以**必须先安装才能看到 SKILL.md/描述**。逻辑不对——用户应能在**安装前**就查看某个技能的
详情（描述、SKILL.md、版本、references）再决定装不装。当前未安装的卡片根本点不开详情。

## 触发场景

在 SkillHub 网格看到一个没装的技能，想先看它到底是什么 → 点不开详情，只能盲装后才看得到。

## 影响

P2：导购体验缺一环（"先看后装"是商店的基本预期）；不涉及数据安全。

## 建议修法

- 后端加"预览"：`GET /api/skills/preview?slug=&name=` —— 若已安装则返回本地详情（installed=true）；
  否则解析 slug，用 skillhub CLI 把 zip 下到**临时目录**读出 SKILL.md/_meta/references，返回同样的
  详情结构（installed=false），随后删临时目录。按 slug 做小缓存避免重复下载。不污染 `~/.workbuddy/skills/`。
- 详情响应加 `installed` 标志。前端 `SkillDetail` 接收「已装 key」或「slug/name」两种入口：
  已装拉本地详情、未装拉预览。未装时页面动作换成「安装」按钮（装完就地刷新为已装态）。
- 前端所有卡片（精选/网格）都可点开详情（不再仅已安装可点）。

## 验证

- 未安装的技能卡可点开详情，SKILL.md 正确渲染（预览/源码可切）；点「安装」后就地变成已装态
  （去试试/启用/打开文件夹/卸载出现）。已安装的仍走本地详情。临时目录不残留、真实 skills 目录不被污染。

## 处理记录（2026-07-07）
- 后端：`skills_store.py` 抽出 `_build_detail(d, installed, name_override)`（详情可从任意目录构造）；
  新增 `preview(slug|name)` —— 已安装→本地详情(installed=true)，未安装→用 CLI 把 zip 下到
  `tempfile.mkdtemp` 读 SKILL.md/metas(installed=false)读完即删，按 slug 小缓存；`routers/skills.py`
  加 `GET /api/skills/preview`（排在 `/{key}` 之前）；详情响应带 `installed` 标志。
- 前端：`SkillDetail` 改为接收 `SkillTarget = {key?|slug?|name?}`——已装拉本地详情、未装拉预览；
  未装时动作换「安装」按钮（转圈，装完 setReloadN 就地刷成已装态、出现去试试/启用/打开文件夹/卸载）；
  头部加「未安装·预览」标。`ExpertsView` 所有卡片（精选/网格/已安装）都可点开详情，传 {key} 或 {name}。
- 验证：模块级 preview 未安装技能返回完整 SKILL.md、installed=false、真实 skills 目录不变、临时目录不残留；
  HTTP live（:8000 已重启）`/api/skills/preview?name=web-tools-guide` 200 installed=false body 3162；tsc + vite build 过。
- commit：（本提交）
