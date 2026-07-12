---
id: WB-130
title: 目录运营中心技能详情缺「文件信息」（SKILL.md 正文/文件树/源码）—— Hub 加单技能拉包代理 + 弹窗渲染
severity: P3
area: fullstack
status: open
origin: 既有实现
files:
  - hub/web/console.html:1570
  - hub/skillhub_sync.py:70
created: 2026-07-12
---

## 问题

WB-127 给「SkillHub 同步」列表加了详情弹窗（`sgDetail()`，
[console.html:1570](../../hub/web/console.html#L1570)），但它只能展示**橱窗卡片元数据**
（名称/描述/分类/★收藏/⬇下载/标签/来源）。技能的**文件信息**——`SKILL.md` 正文、
文件清单/目录树、源码——在 Manager 里**看不到**。

根因是数据源：SkillHub 同步/镜像入库的是榜单 feed 的卡片（[skillhub_sync.py:70](../../hub/skillhub_sync.py#L70)
`data = {**c, ...}`），feed 是列表、不含技能包内容。镜像里根本没有 SKILL.md/文件，
弹窗自然无从展示。

对比：App 客户端**已有**该能力——[WB-056](WB-056-skill-detail-view.md)（详情页渲染 SKILL.md +
预览/源码）、[WB-057](WB-057-skill-detail-preview-before-install.md)（安装前从 SkillHub 拉预览）。
Manager 端未做，因其定位为「浏览/目录运营视图」（弹窗底部原文：「Hub 门户为浏览视图；
安装/试用在 WorkBuddy 客户端」）。

## 触发场景

Manager 控制台 → 目录运营中心 → 技能 → SkillHub 同步（或浏览橱窗）→ 点某技能看详情 →
只见一段描述 + 元数据，看不到它的 SKILL.md 说明/包含哪些文件/源码 → 运营人员想在上架前
判断「这技能内部到底怎么写的」时信息不足。

## 影响

P3：不阻塞（元数据足以做常规目录运营；需读实现的用户可在 App 客户端看）。属能力增强，
且与 Manager「浏览视图」定位存在取舍——是否要在管理端复刻 App 的装机前预览，需先定夺。

## 建议修法

分两层（确认要做后再实施）：
1. **Hub 后端**：加按 slug 拉取单个技能详情/文件的代理端点（复用 WB-094 的直连 HTTP 取数思路，
   拉 SkillHub 的 skill-detail/files 接口；无 key 取公开、企业 key 可选）。返回 SKILL.md 正文 +
   文件清单（+ 可选源码）。注意超时/失败诚实降级（铁律#1，不造假）。
2. **前端**：`sgDetail()` 弹窗按需（打开时懒加载）拉该端点，追加「说明（SKILL.md）」+「文件」段，
   markdown 安全渲染（沿用 App 侧的渲染约定/转义）。续用 `sg-` 前缀防并发撞类名。

替代方案（若定位上不想在 Manager 复刻）：维持现状，弹窗底部「安装/试用在客户端」提示已足够引导，
本 issue 转 `wontfix` 并记明理由。

## 验证

- 明暗双主题：点技能 → 弹窗懒加载出 SKILL.md 正文与文件清单；拉取失败时显示诚实的错误/降级，
  不伪造内容；Esc/遮罩/× 关闭正常。
- 隔离 Hub（:8100 alice/alice123 或 scratchpad DB）+ 真连 SkillHub 实测一个已知技能（如
  ppt-generator-skill）能取到 SKILL.md；后端端点单测/冒烟。
- 无 SkillHub 可达时（离线）降级不崩。
