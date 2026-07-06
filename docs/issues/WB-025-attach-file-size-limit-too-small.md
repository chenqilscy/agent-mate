---
id: WB-025
title: ＋菜单「添加文件」上限 200KB 过小（且被后端 8000 字符截断掩盖）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/components/composer/Composer.tsx:16
  - src/components/composer/Composer.tsx:67
  - backend/agent/runtime.py:53
  - backend/agent/runtime.py:54
  - backend/agent/runtime.py:55
created: 2026-07-06
---

## 问题

Composer ＋菜单「添加文件」把整份文件读成文本作为本轮引用（ref）注入 LLM 输入。
前端在 `Composer.tsx:16` 硬编码 `MAX_ATTACH = 200_000`（≈200KB），
超过就在 `Composer.tsx:67` 弹 toast「文件过大（上限约 200KB 文本）」直接拒收。
用户反馈这个上限太小，稍大一点的文档就传不进来。

需要一并知道的根因链条：**200KB 只是拒收阈值，真正喂给 LLM 的内容远小于此**。
后端 `runtime.py:53-55` 对 ref 有更硬的截断：
- `MAX_REF_BODY = 8000` —— 每个 ref 只保留前 8000 字符（≈8KB）；
- `MAX_REFS_TOTAL = 32_000` —— 所有 ref 合计最多 32000 字符；
- `MAX_REFS = 10` —— 最多 10 个 ref。

所以即便前端放开到 200KB，一份 200KB 文件实际也只有前 8000 字符进模型，其余静默丢弃。
即「前端阈值」与「后端有效上限」两个数字互相矛盾，且都对用户不透明。

（注意：这条与走 `/api/files/upload` 的工作区上传是两条路径——后者 50MB、流式落盘，见 `backend/routers/files.py:30`，不受本 issue 影响。）

## 触发场景

1. 首页/对话 Composer 点 ＋ → 添加文件，选一个 > 200KB 的文本文件（如稍长的 md/日志/csv）。
2. 直接被 toast「文件过大（上限约 200KB 文本）」拒收，无法附加。
3. 退一步选一个 20KB 文件成功附加，但模型其实只看到前 8000 字符——用户无从得知内容被截断。

## 影响

P2：不是崩溃或数据错误，是可用性限制。阻断「附一份中等大小文档让 agent 处理」这一真实高频诉求；
且因前后端两个上限口径不一致、又无截断提示，用户容易误以为整份文件都被读取。择机修。

## 建议修法

不要只把 `MAX_ATTACH` 数字调大——那样只会让更多内容在后端被静默丢弃，问题更隐蔽。整体考虑：

- **对齐前后端口径**：把前端 `MAX_ATTACH` 与后端 `MAX_REF_BODY`/`MAX_REFS_TOTAL` 作为一套来定，
  让「前端允许附加的量」与「实际进模型的量」一致或成合理比例。若要支持更大文件，
  后端 `MAX_REF_BODY`/`MAX_REFS_TOTAL` 需同步上调（注意会吃 LLM 上下文预算，别无界放开）。
- **可选：给 refs 常量集中一处配置**，避免 `Composer.tsx` 与 `runtime.py` 各写各的魔法数。
- **截断要有反馈**：当 ref 内容被后端截断时，让用户可感知（例如附加 chip 上标注「已截断」或在注入块里保留提示）。
- 数值本身取多少（例如提到 1MB / 更大）需与项目约定确认，别拍脑袋；本 issue 先聚焦「口径对齐 + 截断可见」。

## 验证

- 附加一个略大于旧上限的文本文件，能成功附加，不再被误拒。
- 附加内容超过后端 `MAX_REF_BODY` 时，用户能看到「已截断」类提示，且实际注入 LLM 的长度符合新约定（手动跑一次带 ref 的 `/chat`，确认注入块长度）。
- `npx tsc --noEmit` 通过；改后端则 `python -m py_compile backend/agent/runtime.py`。
- 明暗双主题下 toast/chip 提示均可见（视觉零重设计、暗色不翻车）。

## 处理记录（2026-07-07）

按用户拍板的口径：**每个 ref 有效上限 ≈1MB**（放大而非仅调数字，且截断可见）。

- 前端 `src/components/composer/Composer.tsx`：
  - `MAX_ATTACH` 200KB → **4MB**（硬性 payload 上限，仍守 WB-010 不让单次附件撑爆内存/请求体）；
    新增 `EFFECTIVE_REF_LIMIT = 1_000_000`，注释与后端 `MAX_REF_BODY` 互相指认，作为「实际注入 LLM 的每 ref 字符数」。
  - `onFileChosen`：超 4MB 仍拒收（文案改为「上限约 4MB 文本」）；成功附加时，若文本 > 100 万字符，
    toast 明确「注入时会截断至前 100 万字符」。
  - ref chip：当 `content.length > EFFECTIVE_REF_LIMIT` 时，chip 名后缀「· 已截断」并在 `title` 说明——
    复用既有 `.np-lbl` 文本、无新增 CSS/写死颜色，随主题走，暗色不翻车。
- 后端 `backend/agent/runtime.py`：
  - `MAX_REF_BODY` 8000 → **1_000_000**，`MAX_REFS_TOTAL` 32_000 → **4_000_000**（`MAX_REFS=10` 不变）。
  - 注入循环：截断时在该 ref 块内追加 in-band 标记「[⚠ 内容已截断：仅注入前 N 字符，原文共 M 字符]」，
    不再静默丢弃。
- 验证：
  - `npx tsc --noEmit` 通过；`py_compile backend/agent/runtime.py` 通过。
  - 后端按 live 常量实测注入逻辑：300k 字符 ref → 全量注入 300000、无标记；1.2M 字符 ref → 注入 1000000、
    带截断标记「injected 1000000 of 1200000」。即「注入长度符合新约定」。
  - 前端 chip/toast 为确定性的长度判断（已 tsc 通过，且经 Vite HMR 推入用户正在运行的窗口）；
    截断提示走既有 chip 文本样式、无主题翻转风险。浏览器 profile 被用户当前 App 窗口占用（SingletonLock），
    未强杀以免打断用户；用户可在开着的窗口直接附一个 >200KB / >1MB 文本文件眼见 chip 与 toast。
- commit：随本次提交（master，标题带 WB-025）。
