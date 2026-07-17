---
id: WB-192
title: run_command 子进程继承后端全部密钥（WB-011 只堵了连接器那条路）—— 模型一句 echo 就能读走 LLM_API_KEY
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/tools.py:175
  - backend/agent/mcp_client.py:75
  - backend/agent/tools.py:206
created: 2026-07-17
---

## 问题

`_run_command_run`（`backend/agent/tools.py:175`）：

```python
proc = subprocess.run(command, shell=True, cwd=str(current_root()), capture_output=True, text=True, timeout=CMD_TIMEOUT)
```

**没有 `env=`** → 子进程继承后端进程的整个 `os.environ`，而 `config.py` 的 `load_dotenv` 已把
`backend/.env` 里的 `LLM_API_KEY` / `WEKNORA_API_KEY` / `TELEGRAM_BOT_TOKEN` / `GITHUB_TOKEN` /
`KDOCS_TOKEN` 全写进了 `os.environ`。

于是 agent 只要 `echo $LLM_API_KEY`（或 `env`、`set`、任意脚本读 env）就能把密钥读进
**模型上下文** → 随下一轮请求**上传给 LLM 厂商**（本项目默认 DeepSeek），并进消息持久化、
可被「设置 · 数据管理」导出（WB-149）。这与铁律#4「密钥只存后端、绝不进前端/不透传给子进程」直接冲突。

**这正是 WB-011 修过的同一类洞，但只堵了一条路**：WB-011 把 `open_connectors`（`mcp_client.py:75`）
的 MCP 连接器子进程 env 收成「无密钥白名单」；`run_command` 这条从未收口。
WB-014（run_command 非真沙箱）当年是以「工具描述里**如实标注**非真沙箱」结的案，没有动 env。

相关放大面（同一条路上的既有设计，不是本 issue 要改的，但一起考虑才完整）：
- `pre=lambda a: {"kind":"step","tool":"run_command","label": f"运行命令 {a.get('command','')[:80]}"}`
  （`tools.py:206`）→ 命令行原文进 SSE trace → **进前端 UI**；
- `security.audit(owner, "run_command", command, "executed")` → 命令行原文进审计表（明文）。
  故任何「让模型把 token 拼进命令行」的方案（如 skill 教用 CLI），泄漏面是
  前端 + 审计表 + 模型上下文 + 第三方 LLM 服务器四处，而不止本机进程列表。

## 触发场景

任一 exec 模式会话（有 run_command 工具）：
> 用 run_command 执行：`echo $LLM_API_KEY`

→ 密钥出现在工具输出 → 进模型上下文与消息记录。
实证（2026-07-17，未打印密钥值）：在与后端相同的加载路径下 `import config` 后，
`subprocess.run(..., shell=True)` 的子进程读到 `LLM_API_KEY` 长度 35、`WEKNORA_API_KEY` 存在。

安全中心（WB-152）的命令黑名单是**用户自配的正则**，默认不含 `echo $LLM_API_KEY` 这类，
且黑名单永远拦不住等价写法（`env`、`printenv`、`python -c "import os;..."`），不能算缓解。

## 影响

P1：密钥外泄路径，且是模型可自主触发的。虽然本项目 local-first、后端只绑 127.0.0.1，
但泄漏终点是**第三方 LLM 厂商**与前端/导出文件，超出「密钥不出本机」的承诺。
提权门槛低（一条自然语言指令即可），且用户对此无感知。

## 建议修法

照 WB-011 已验证的做法，把同一套「无密钥白名单」用到 `run_command`：

- `subprocess.run(..., env=<白名单 env>)`：以 `os.environ` 为基，**剔除** `config.Settings` 里
  声明的全部密钥字段（`LLM_API_KEY`/`WEKNORA_API_KEY`/`TELEGRAM_*`/`GITHUB_TOKEN`/`KDOCS_TOKEN`…），
  最好从 `Settings` 反射出「密钥名单」，避免将来加了新密钥忘记同步（WB-011 的白名单可复用/共用一处）。
- 注意别把 `PATH`/`SYSTEMROOT`/`PYTHONUTF8` 之类必需变量一起剔掉（Windows 下缺 `SYSTEMROOT` 会让很多进程起不来）。
- 需要凭据的 CLI（如 `kdocs-cli`）不应靠 env 透传：它自带 keychain 登录
  （`kdocs-cli auth login`，见 `mcp_servers/kdocs.py` 头注释），凭据由 CLI 自己持有；
  确需注入时应走连接器那条路（后端代跑 + 定向注入），而不是把密钥丢进通用 shell 的 env。

## 验证

- 修后：`run_command` 执行 `echo $LLM_API_KEY` / `env | grep KEY` 应拿不到任何密钥值。
- 回归：`run_command` 仍能正常跑普通命令（Windows 下 `SYSTEMROOT`/`PATH` 未被误删，
  `python`/`node` 等仍可执行）；沙箱 cwd 与超时行为不变；WB-152 黑名单与审计不受影响。
- 与 WB-011 共用密钥名单后：连接器路径回归（GitHub/Telegram/kdocs 连接器仍能拿到自己该拿的那一个）。

## 处理记录（2026-07-17）

- 改动：
  - `backend/config.py`：`load_dotenv` 包一层 `_load_env`，记下**本次 .env 实际读入的键名**
    （`dotenv_values`）；导出 `SECRET_ENV_KEYS`（= .env 键名 ∪ `Settings` 上按名字模式
    `_KEY/_TOKEN/_SECRET/_PASSWORD/_PASSWD/_CREDENTIAL` 识别出的字段）与 `scrubbed_env()`。
  - `backend/agent/tools.py`：`_run_command_run` 的 `subprocess.run(...)` 加 `env=scrubbed_env()`。
- **与原「建议修法」的偏离（有意）**：原建议「照 WB-011 用白名单」。实际改用**精确剔除**——
  WB-011 的 `_SAFE_ENV` 白名单只放行 PATH/SYSTEMROOT 等 22 个变量，那对连接器成立
  （只跑已知的 MCP server），但 `run_command` 要跑用户的**真实命令**（npm/git/python/代理…），
  白名单会误伤（如 `HTTP_PROXY`、`VIRTUAL_ENV`、`NODE_*` 全没了，且本机在国内、代理变量是刚需）。
  剔除名单以 **.env 实际键名**为准而非硬编码，故将来往 .env 加新密钥**自动**被覆盖，
  不存在「忘了同步名单」的漂移；`Settings` 的模式识别再兜住「用真实环境变量而非 .env 配」的情况。
- **范围诚实声明**：本改动只保证「后端不主动把**自己的**密钥递给通用 shell」，
  **不把 run_command 变成沙箱** —— WB-014「非真沙箱、命令以后端权限执行」的结论依然成立；
  用户自己 shell 环境里的其它密钥（本就不是后端的）不在本 issue 射程内。
  同一条路上的另外两处放大面（命令行原文进 SSE trace→前端、进审计表明文）本次未动，
  属独立取舍（用户需要看到 agent 到底跑了什么），如需脱敏另开。
- 验证（真跑，非推演）：
  - 端到端走**真 `run_command` 工具**（set_security_context + use_root 后直接调 `run`）三条攻击路径：
    ① `python -c "print(os.environ.get('LLM_API_KEY'))"` → `None`；
    ② `echo %LLM_API_KEY%` → 原样输出 `%LLM_API_KEY%`（未展开＝未设）；
    ③ 列出所有含 KEY/TOKEN/SECRET 的变量名 → `[]`（一个都没有）。
  - 回归：`python -c "print(1+1)"` → 2、`echo hello` → hello（正常命令不受影响）；
    `scrubbed_env()` 保留 PATH/SYSTEMROOT/COMSPEC/TEMP/USERPROFILE（env 95 → 86 项，只掉 9 项）。
  - 未误伤后端自己用密钥：`POST /api/knowledge/config/test` → `{ok:true, kb_count:1}`
    （证明 `os.environ` 未被改动，只是子进程看不到）。
  - 未误伤连接器（WB-011 那条路）：`mcp_client` 的 `_safe_base_env`/`_secret_env` 未被本次触碰；
    内置 server（如 `telegram.py` 的 `os.environ.get("TELEGRAM_BOT_TOKEN")`）仍从注入的 secret_env 取。
  - `py_compile` 通过（config.py / tools.py）。
- commit：见下方。
