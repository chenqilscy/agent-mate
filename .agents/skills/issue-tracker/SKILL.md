---
name: issue-tracker
description: 登记与处理 AgentMate 的问题（issue）台账（docs/issues/）。当用户要「登记/记录一个问题」「新建 issue」，或「处理/修复某个 issue」「看还有哪些 issue」时使用。定义了从发现→登记→处理→验证→关闭→自动提交的完整流程。
---

# AgentMate Issue Tracker

AgentMate 的问题台账在 `docs/issues/`。核心规矩：**所有问题先登记成一条 issue，再处理**。
活动问题 = 一个文件 + `README.md` 活动台账里的一行；终态问题合并进入只读归档卷。

## 目录约定

- 活动台账：`docs/issues/README.md`，只镜像 `open` / `in-progress` / `deferred`。
- 活动 issue：`docs/issues/WB-<###>-<slug>.md`，编号三位递增、不复用。
- 终态归档：`docs/issues/archive/<year>/WB-<start>-<end>.md`，保存 `fixed` / `wontfix` 的完整元数据、正文、处理记录和稳定 `#wb-###` 锚点；卷索引在 `docs/issues/archive/README.md`。
- 活动状态以独立文件 frontmatter 为权威；归档后以归档记录中的原始 frontmatter 为权威。不要手工拆分或编辑生成的归档结构。
- 归档与校验统一使用 `python scripts/archive_issues.py --apply|--check|--next-id`。

## Issue 文件模板

```markdown
---
id: WB-###
title: 一句话标题
severity: P0 | P1 | P2 | P3
area: frontend | backend | ui | misc
status: open | in-progress | fixed | deferred | wontfix
origin: 🆕 近期改动 | 🏚 迁移遗留 | 既有实现
files:
  - path/to/file.ext:line
created: YYYY-MM-DD
---

## 问题
（是什么、根因，带 `文件:行号`）

## 触发场景
（具体输入/操作序列 → 错误结果，可复现）

## 影响
（严重度理由）

## 建议修法
（怎么改，尽量给到文件/思路，别过度规定实现）

## 验证
（修完怎么确认修好了）
```

严重度：`P0` 立即修 · `P1` 尽快修 · `P2` 择机修 · `P3` 备忘。

## 流程一：登记新 issue

1. **先查重**：在 `docs/issues/`（含 `archive/`）检索同一根因；归档项复发时登记新 issue 并引用旧 ID，不修改历史归档。
2. **确认属实**：对照源码定位到 `文件:行号`，能说清触发场景。审查类问题**报告前必须核实**，不臆测。
3. **取编号**：运行 `python scripts/archive_issues.py --next-id`，同时统计活动文件与归档记录，禁止只看根 README。
4. **建文件**：按模板写 `WB-###-<slug>.md`，`status: open`。slug 用简短英文短横线。
5. **登台账**：在根 README 活动表按编号顺序插一行（状态 ⬜、严重度、领域、标题+相对链接）。
6. 登记阶段**只登记、不改代码**。

## 流程二：处理 / 修复一个 issue

1. **认领**：把该 issue frontmatter `status` 改为 `in-progress`，README 对应行状态改 🟡。
2. **读上下文**：先读 `AGENTS.md` 与该 issue 的「建议修法」；遵守项目铁律（见下）。
3. **改代码**：范围收敛到这一个 issue；顺手发现的新问题另开 issue，不夹带。
4. **自检**：
   - 前端：`npx tsc --noEmit` 必须过；涉及 UI 的改动尽量在浏览器（Playwright）实测，明暗双主题都看。
   - 后端：`python -m py_compile <改动文件>`；涉及运行时的改动手动跑一次相关请求验证。
5. **按 issue 的「验证」小节核对**，确认真的修好（明暗主题、边界输入、回归旧路径）。
6. **关闭并归档**：先把独立文件改为 `status: fixed`（或写明理由后改 `wontfix`），在文件末尾追加一小节：
   ```markdown
   ## 处理记录（YYYY-MM-DD）
   - 改动：<文件与要点>
   - 验证：<如何验证、结果>
   - commit：<哈希，如已提交>
   ```
   然后运行 `python scripts/archive_issues.py --apply`：该独立文件会并入对应归档卷，根 README 活动行自动移除，仓库内指向旧文件的 Markdown 链接自动改到稳定锚点。最后必须运行 `--check`。
7. **自动提交**：issue 修复、验证并归档后，默认立即创建 commit，不再等待用户再次要求。仅当用户明确要求不提交，或工作树中的外部改动无法与当前 issue 安全隔离时停止提交并说明原因。
   - 只暂存当前 issue 的删除、对应归档卷、两个索引和本次实现涉及的文件；不得用 `git add .` / `git add -A` 把未知改动一并纳入。
   - 一条 commit 对应一个（或一组同源）issue，标题必须带 `WB-###`。
   - 提交前运行敏感文件自检：`git diff --cached --name-only | grep -iE "\.env$|node_modules|\.venv|\.db|/workspace/|\.png$|\.playwright"`，结果必须为空。
   - commit 信息结尾添加：`Co-Authored-By: Codex Opus 4.8 (1M context) <noreply@anthropic.com>`。
   - 提交后核对 commit 内容与剩余工作树，确认没有夹带其他人的改动。

`deferred` 仍是活动状态并留在根目录；`wontfix` 必须写明理由后归档。

## 项目铁律（改代码时必须遵守）

- **不硬编码、不模拟**：流式来自真实 LLM，状态真持久化，trace 来自真实事件。
- **视觉零重设计**：CSS class 名与设计 token 沿用腾讯 WorkBuddy 参考原型（`docs/WorkBuddy/tencent-workbuddy-reference.html` / `src/styles/`）；暗色是 `body.dark` 上的变量覆盖，别写死会在暗色翻车的浅色背景。
- **API Key 只存后端** `backend/.env`，绝不进前端/提交/子进程环境。
- **SSE 协议是前后端契约**：一种事件类型 ⇄ 一种 UI 形态（`backend/agent/events.py` ⇄ `src/stores/chatStore.ts`）。
- 详见 `AGENTS.md`。

## 常用命令

```bash
# 前端类型检查 / 构建
npx tsc --noEmit
npx vite build
# issue 归档一致性（仓库根目录）
python scripts/archive_issues.py --check
# 后端编译检查
cd backend && ./.venv/Scripts/python.exe -m py_compile <files>
# 启动（详见 README）
cd backend && ./.venv/Scripts/python.exe main.py     # :8101
pnpm dev                                              # :8102
```
