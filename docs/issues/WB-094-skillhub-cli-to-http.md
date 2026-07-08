---
id: WB-094
title: SkillHub 取数从 CLI 子进程改为直连 HTTP（去 CLI 依赖 + 拿到发布时间）
severity: P3
area: backend
status: open
origin: 用户「后期考虑不用 CLI，改 API 方式」+ API key 调研
files:
  - hub/skillhub_client.py
  - hub/skillhub_sync.py
created: 2026-07-08
---

## 问题

Hub 当前 SkillHub **rankings（镜像同步）走 CLI 子进程**（`skill rankings --type all`），依赖本机装 `~/.skillhub` CLI、
有自升级/GBK/超时等脆弱点、且部署不可移植。search 已直连 HTTP，rankings 没有。

## 调研结论（2026-07-08，实测 api.skillhub.cn）

- **读目录全是公开 HTTP、不需要 key**：
  - rankings = 6 个 showcase 端点 `GET /api/v1/showcase/{hot,featured,newest,recommended,trending,paid}`（实测 200）。
  - search = `GET /api/v1/search?q=&limit=`（实测 200，富字段）。
- **API key 分两类**（CLI 明说）：`skh_...`=**个人社区版 user token（发布用）**；`sk-ent-xxx`=**企业 key（组织私有 registry）**。
  用户给的 `skh_...` 打 `POST /api/v1/registry/verify` 返回 **401**——它是发布/个人 token，**读公开目录用不上、也不需要**。
- **HTTP search 比 CLI 多返回 `created_at`/`updated_at`**（CLI `_normalize_card` 丢了）→ 可支撑
  「最近上新」排序（补上 [WB-092](WB-092-skillhub-tab-parity.md) 的缺口）。**仍无 api-key-需求字段**——那个筛选数据源确实给不了。

## 建议修法（后期）

- `skillhub_client.rankings_all()` 改为直连 6 个 `showcase/*` HTTP 端点（httpx，白名单无凭据），CLI 仅作可选兜底（或彻底移除）。
- `_normalize_card` 保留 `created_at`/`updated_at`；`skillhub_sync` 入库带上 → 前端加「最近上新」排序。
- 企业私有 registry（`sk-ent-` key）作可选增强：配了企业 key 才拉 org 私有 skills，未配就纯公开目录。
- 凭据管理：任何 key 只进 gitignored env（`SKILLHUB_TOKEN` 个人 / `SKILLHUB_API_KEY` 企业），绝不提交（铁律#4）。

## 验证

去掉 CLI 后 rankings/search 仍出全量目录；镜像项带 `created_at`；无 CLI 环境也能同步；企业 key（若配）拉到私有 skills。
