---
id: WB-053
title: 共享工作区提交纪律 —— 并发会话下别整文件 git add，按 hunk 暂存
severity: P3
area: misc
status: open
origin: 既有实现
files:
  - docs/issues/README.md
  - CLAUDE.md
created: 2026-07-07
---

## 问题

本仓库常被**多个 Claude Code 会话并发开发，且共享同一个工作区与 git index**
（同一台机、同一个 `d:\work\local\buddy`）。多个会话会**同时**编辑同一批文件，
彼此的改动在工作区里交织、且互相看不见对方的未提交状态。

后果：一次 `git add <共享文件>` 或 `git add -A` / `git add .` 会把**别的会话尚未提交的
改动一并卷进你的提交**，从而：
- 违反项目「一 commit 对应一个 issue」（WB-###）；
- 把别人**未完成/未验证**的工作错误归属到你的 commit；
- 甚至提交进半成品代码。

这是反复踩到的坑（见 `project-state.md` 里多条 COORDINATION 记录：连接器 / A2 sidecar /
M7 协作 / WB-051）。最新一次：**WB-051（Telegram 连接器）**提交时，另一会话正在建
**WB-052（金山文档/kdocs 连接器）**，两者改到**同一批共享文件**——`backend/agent/mcp_client.py`
的 `CONNECTORS`、`backend/config.py`、`backend/.env.example`、`src/data/catalog.ts`、
`docs/issues/README.md` 台账行。一次朴素的 `git add src/data/catalog.ts` **确实**把对方的
kdocs 前端改动扫进了我的暂存区（而且对方还在我操作期间把 README 的 WB-052 行重新加回来）。

## 触发场景

1. 会话 A 与会话 B 各自在做不同 issue，都改了 `mcp_client.py` / `config.py` /
   `catalog.ts` / `docs/issues/README.md` 等热点文件。
2. A 执行 `git add <文件>` 或 `git add -A` 后 `git commit`。
3. B 的未提交改动被一起提交进 A 的 commit → 归属错乱 + 半成品入库。

**易撞车的热点共享文件**（据历史）：`backend/agent/mcp_client.py`（CONNECTORS 注册表）、
`backend/config.py`、`backend/.env.example`、`src/data/catalog.ts`、`docs/issues/README.md`
（台账）、`src/components/Sidebar.tsx`、`src/styles/app.css`、`src/lib/api.ts`、
`src/types.ts`、`backend/storage/db.py`、`backend/agent/runtime.py`。

## 影响

P3（备忘/流程）：不构成代码缺陷，但一旦发生就污染 git 历史、错误归属、可能提交半成品，
排查与回滚成本高。属于**必须遵守的提交纪律**，故落成对所有会话可见的一条 issue（记忆文件
只有单个会话读得到）。

## 建议修法（提交纪律 —— 在本仓库提交时必须遵守）

1. **默认假设**：提交前，其他会话可能正在改你要动的同一批文件。
2. **绝不整文件暂存共享文件**：不用 `git add <共享文件>`、`git add -A`、`git add .`。
   只暂存**属于你这个 issue 的 hunk**。
3. **按 hunk 暂存**用 `git apply --cached`（`git add -p` 是交互式、本环境不可用）：
   - 用「HEAD 原文 + 你已知的改动」经 difflib 生成补丁（上下文/计数才精确、LF/UTF-8），
     再 `git apply --cached`。它**只改 index、不碰工作区**，对并发写是安全的。
     参考脚本思路见 `project-state.md`（scratchpad 里的 `mk_patch.py` / `stage_hunks.py`）。
   - 若不慎把别人的改动暂存了：`git restore --staged <文件>` 撤回，重新按 hunk 打补丁。
4. **提交前复核暂存区**：`git diff --cached | grep -iE "<别人功能的关键字>"` 必须为空
   （如本次用 `kdocs|KDOCS|金山文档|WB-052|ConnTool`）。再跑既有敏感文件自检：
   `git diff --cached --name-only | grep -iE "\.env$|node_modules|\.venv|\.db|/workspace/|\.png$|\.playwright"` 也应为空。
5. **新文件可以按精确路径 `git add`**（新文件不可能含别人的改动），但仍**不要** `git add .`。
6. **台账（README.md）是共享文件**：只 hunk-暂存你自己那一行；预期并发会话会不断加回自己的行，
   别去删对方的行。
7. **编号可能撞号**：两个会话可能同时取「当前最大 +1」拿到同一个 WB-###。取号后、提交前
   再核一次 README 的真实最大编号；发现撞号就顺延重编。
8. 保持**一 commit 一 issue**，commit 标题带 `WB-###`。

> 说明：这条纪律理想上也应写进 `CLAUDE.md` 的「Git」小节（所有会话都读它作为项目指令）。
> 本 issue 先作为可追溯的登记与详细说明；是否并入 CLAUDE.md 由后续处理该 issue 时决定
> （改 CLAUDE.md 本身也要按上述 hunk 纪律，因为它同样是热点共享文件）。

## 验证

- 一次提交后 `git show --stat HEAD` / `git diff HEAD~1` 只包含你这个 issue 的文件与 hunk，
  无其他会话的功能关键字。
- 该纪律为标准做法后，`project-state.md` 的 COORDINATION 记录不再出现「误把对方改动提交」的复盘。
