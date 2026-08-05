---
id: WB-419
title: 本地 Server 测试账号凭据文件应被忽略且不入库
severity: P3
area: backend
status: fixed
origin: 测试体系配套（functional/regression/e2e 测试用例落地时复用可复用登录凭据）
files:
  - .gitignore:13
  - README.md:90
created: 2026-08-05
---

## 问题

本地 Server（`:8100`）受控试用需要可复用的测试账号（用户名可共享、密码不可提交）。若把含密码的
`docs/local-test-accounts.md` 误提交，会泄漏登录凭据，违反密钥只存后端、绝不提交的铁律。

## 影响

P3（合规）：仅影响仓库卫生与凭据安全；不影响运行时功能。该文件本身是可选的本地产物，不存在于纯净克隆中。

## 建议实施

1. 在 `.gitignore` 追加 `docs/local-test-accounts.md`，确保密码永不被 `git add` 捕获。
2. 在 `README.md` 的运行说明后补充一段，说明该文件的存在目的、被忽略原因与仅可用于本地/受控测试库。

## 验证

- `git check-ignore docs/local-test-accounts.md` 命中对应规则；
- `git status` 在创建该文件后不将其列为待跟踪；
- `README.md` 新增段落明确「含登录密码、故意忽略、仅用于本地或显式指定的受控测试库」。

## 处理记录（2026-08-05）

- 状态：`fixed`/✅。`.gitignore` 已忽略 `docs/local-test-accounts.md`，`README.md` 已文档化其用途
  （提交 `abb80ed`，本 issue 编号后补登记）。
- 配套：本地优先/Server 测试套件（`backend/tests/functional/test_F_ask_user.py`、
  `backend/tests/regression/test_server_localfirst_fallback.py`、`test_collaboration_role_matrix.py`、
  `test_server_pull_mirror.py`、`backend/tests/e2e/visual_theme_check.py`）此前已随 WB-344/366..373 入库，
  本次无新增测试代码改动，仅补凭据不入库的配套。
