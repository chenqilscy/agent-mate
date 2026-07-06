---
id: WB-050
title: 非成员可把 /chat 指向他人项目 —— 新建会话分支未校验 project 访问权，run 在该项目沙箱内执行
severity: P2
area: backend
status: fixed
origin: 细致功能自动化测试（test_B B8）实测发现
files:
  - backend/routers/chat.py:57
  - backend/agent/runtime.py
created: 2026-07-07
---

## 问题

`POST /api/chat` 的**新建会话分支**（不带 `session_id`）直接用请求体里的 `project_id`
建会话、且**不校验调用者对该项目的访问权**：

```python
# backend/routers/chat.py — 新建会话分支
session = db.create_session(
    owner_id=user.id,
    title=title,
    kind="projexec" if body.project_id else "chat",
    space=body.space,
    project_id=body.project_id,        # ← 任意 project_id，无 _require_access 校验
)
```

对照同文件里**已有会话分支**（带 `session_id`）是 owner-scoped 的
（`db.get_session(body.session_id, owner_id=user.id)`，WB-013 注释在此），
新建分支却漏了访问校验。而 `runtime.run_chat` 会按 `session.project_id`
把沙箱根切到 `project_root(session.project_id)`（见 `agent/sandbox.py`）。

后果：任一**已登录用户**只要知道/猜到某个 `project_id`，就能
`POST /api/chat {text, project_id: <他人项目>}`，让本轮 run 在**他人项目的工作区沙箱**里
执行 `write_file` / `read_file` / `list_dir` / 工作区检索连接器 —— 即**跨项目读写该项目云盘文件**。

计划项写回是安全的（`set_work_item_status` 另有 owner+project 双重校验），
但**工作区文件级访问未设闸**。

## 影响

- 属 M7 多账户下的 owner/member 隔离缺口，与 WB-013（files 路由跨项目读，已修）同源但**位于 chat 入口**，WB-013 的 files 路由修复未覆盖此路径。
- 触发前提：攻击者需为**已登录账户**且**知道目标 project_id**（UUID，不易枚举），故非高危；但被移出项目的前成员仍记得 id 即可越权，故需修。
- 单机免登录模式不受影响（只有本地所有者一个身份）。

## 复现

test_B 的 B8：
1. 账号 A 建项目 P；账号 S（非 P 成员）登录。
2. `POST /api/chat {text:"...", project_id: P.id}`（S 的 token）。
3. 现状返回 **200 并开始在 P 的沙箱内执行**；期望 **403/404**。

## 建议修法

在 chat.py 新建会话分支里，`body.project_id` 非空时先校验访问权（与 projects 路由一致）：

```python
if body.project_id and db.project_access_role(body.project_id, user.id) is None:
    raise HTTPException(404, "project not found")
```

（可选）Viewer 只读项目是否允许发起执行（写沙箱）由产品定；若不允许，Viewer 也应 403。
修后回归：非成员 → 404；成员 → 200；单机免登录 → 照常。

## 验证

- test_B 的 B8 断言从 FAIL 转 PASS（非成员 `/chat` 指向他人项目返回 403/404）。
- 成员/所有者对自有项目发起执行仍 200。
- 单机免登录模式新建任务/项目执行不受影响。

## 处理记录

2026-07-07 fixed（commit 见 `fix(WB-050)`）：
- `backend/routers/chat.py` 新建会话分支（无 `session_id`）在建 session 前加一行访问校验：
  `if body.project_id and db.project_access_role(body.project_id, user.id) is None: raise HTTPException(404, "project not found")`，
  与带 `session_id` 分支的 owner-scoping 对齐。
- 硬重启 `:8000` 加载新代码后回归：`backend/tests/functional/test_B_projects.py` 的 **B8** 由 FAIL 转 **PASS**
  （非成员 `/chat {project_id: 他人项目}` → 404）；成员/所有者对自有项目仍 200；单机免登录模式不受影响。
- 全套细致功能测试（A/B/C/D）在修复后 **72/72** 全绿。
