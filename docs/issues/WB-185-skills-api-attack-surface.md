---
id: WB-185
title: /api/skills 攻击面 —— App 侧 install/preview 的 slug 未校验（WB-160 只修了 Hub 孪生站点）+ 九端点零鉴权
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/skills_store.py:401
  - backend/agent/skills_store.py:240
  - backend/routers/skills.py:22
  - backend/routers/skills.py:76
  - hub/skillhub_client.py:32
created: 2026-07-16
---

## 问题

### 1. slug 未校验（WB-160 的孪生漏网）

[skills_store.py:401-417](../../backend/agent/skills_store.py) `install(slug)`：

```python
slug = (slug or "").strip()
if not slug: return {...}
root = skills_dir()
cp = _run_cli(["install", slug, "--dir", str(root), "--json", "--force"], timeout=180)
dest = (root / slug)          # ← slug 原样拼路径
```

`slug` **无任何白名单校验**就（a）拼进 `root / slug` 路径、（b）原样进 CLI argv。
`preview()`（`:240-245`）同理 `tmp / slug`。
`POST /api/skills/install` 的 `InstallBody.slug`（`routers/skills.py:22-24`）也**无 validator**。

**WB-160 第 6 项已修的是 `hub/skillhub_client.py`**（加了 `_SLUG_RE = ^[A-Za-z0-9._-]+$` + 拒 `..`），
其 `files:` 清单里**只有 hub 侧**，App 侧这个孪生站点从未在其范围内 → **同根因、漏网**。
两侧现在校验口径不一致。

注意 `_safe_dir()`（`:40-49`）只保护 **key** 类操作（uninstall/toggle/reveal/detail），
**保护不到 slug 路径**。

风险面：`slug="../../x"` 路径穿越；`slug="--dir"` 之类 CLI 参数注入
（argv 传参，非 shell，无 shell 注入，但可污染 CLI 参数解析）。

### 2. 九个端点零鉴权

`backend/routers/skills.py` 全文**没有任何端点依赖 `current_user()`**，
`AuthMiddleware` 只填 contextvar 不拦截。其中包括副作用很重的三个：

- `POST /skills/install` → 跑子进程下载解压
- `POST /skills/{key}/uninstall` → `shutil.rmtree`
- `POST /skills/{key}/reveal` → `os.startfile` / `open` / `xdg-open`

设计注释（`skills.py:1-5`）称「技能是每机器的磁盘资源，不按 owner 隔离」——
单机 local-first 下成立，但 **WB-153 已确立共享后端的威胁模型**，
彼时任何登录用户都能卸载/安装他人机器上的技能、甚至触发 `reveal` 在宿主机弹窗口。

## 触发场景

1. `POST /api/skills/install {"slug": "../../../evil"}` → 后端拼出 `SKILLS_DIR/../../../evil`。
2. 共享后端部署下，任意（甚至未登录）客户端 `POST /api/skills/{key}/uninstall` → 删掉宿主机技能目录。

## 影响

P2。单机默认部署下风险有限（后端只绑 `127.0.0.1`），但：
（a）slug 校验是**已修 bug 的孪生漏网**，修复成本极低，两侧口径应一致；
（b）零鉴权在共享后端模式下与 WB-153 的加固方向冲突。

## 建议修法

1. **slug 校验**：把 `hub/skillhub_client.py:32-36` 的 `_SLUG_RE` / `_valid_slug` 同步到
   `backend/agent/skills_store.py`，`install()` / `preview()` / `resolve_slug()` 入口统一校验；
   `InstallBody.slug` 加 pydantic pattern。**与 Hub 侧逐字一致**，避免再次分叉。
2. **鉴权**：`/api/skills` 的**写端点**（install/uninstall/toggle/reveal）加 `current_user()` 依赖；
   读端点（list/search/rankings/preview/detail）可保持开放或同样加。
   保持「不按 owner 隔离」的设计（技能是机器级资源），但**要求是个已认证的人**。
   单机 `LOCAL_USER` 注入下行为不变。

## 验证

- `py_compile` 过。
- `POST /api/skills/install {"slug":"../x"}` / `{"slug":"a/b"}` / `{"slug":"--dir"}` → 全部 400 拒绝；
  正常 slug（`^[A-Za-z0-9._-]+$`）仍能装。
- 两侧口径一致：diff `skills_store.py` 与 `hub/skillhub_client.py` 的 slug 校验逻辑。
- 未带 token 调 `POST /skills/{key}/uninstall` → 401；单机默认（LOCAL_USER）下安装/卸载仍正常。
- 回归：技能页安装/卸载/启停/打开文件夹全链路仍通。

## 处理记录（2026-07-16）

2 项中**修 1 项（slug 校验）**，**鉴权项 ⏸ deferred**（理由见下）。

### ✅ slug 校验（已修）

- **`backend/agent/skills_store.py`**：新增 `_SLUG_RE` + `valid_slug()`，与
  `hub/skillhub_client.py` 同一口径。接入三处：
  - `install()` —— 非法 slug 直接 `{"ok": False, "error": "非法 slug：…"}`，不触达 CLI；
  - `preview()` —— 非法 slug 返回 `None`；
  - `resolve_slug()` —— **远端搜索返回的 slug 也过白名单**（它会流进 install 的路径拼接，
    不因「来自 SkillHub」就当可信）。
- **`backend/routers/skills.py`**：`install` / `preview` 端点对非法 slug 返回 **400**
  （客户端错误，而非落到 install 的 502「安装失败」）；preview 的校验**前置于 Hub 代理调用**
  ——slug 还会被拼进发往 Manager 的 URL。

### ✅ 顺带硬化：前导 `-`（两侧同步）

验证时实测发现 **WB-160 原修法没盖住的残留**：`--dir` 这类 slug **字符集合法、白名单放行**，
但会原样进 `_run_cli(["install", slug, "--dir", …])` 的 argv。真实证据（修复前打真后端）：

```
POST /api/skills/install {"slug":"--dir"}
→ 502 {"detail":"usage: skills_store_cli.py install [-h] [--files-base-uri …]"}
   ← skillhub CLI 的 argparse 真被噎住，参数注入向量确认可达
```

故 `valid_slug` 另拒前导 `-`。**同步改了 `hub/skillhub_client.py:_valid_slug`** ——
只改 App 侧会让我刚统一的口径立刻再次分叉，而这正是本 issue 要根治的问题。
（argv 传参，无 shell 注入；风险限于 CLI 参数解析被污染。）

### ⏸ 九端点零鉴权（deferred —— 原「建议修法」有误，在此更正）

原修法写的「加 `current_user()` 依赖 → 401」**不成立**：
`backend/auth/deps.py:46-47` 的 `current_user()` **从不拒绝**，无 token 即回退 `LOCAL_USER_ID`，
这是 M7 的显式设计（deps.py 文件头："No token → the fixed local owner, so single-machine use
keeps working without logging in"）。全后端**没有任何「要求已认证」的原语**，
grep `REQUIRE_AUTH|MULTI_USER|require_auth` 零命中。

因此给技能端点加 `Depends(current_user)` **一个洞都堵不上**，只会造出一个看起来在鉴权、
实则不拦的假依赖 —— 比现状更糟，且违反铁律#1 的精神。

真正要做的是**引入共享后端模式的鉴权策略**（一个 mode 开关 + 一个会拒绝的 dep），
这是**跨所有路由的横切决策**，不是技能侧能单独修的东西，也不该在本 issue 里夹带。
留待共享后端部署形态明确后另立 issue（与 WB-153 同一主线）。

单机默认部署（后端只绑 `127.0.0.1`）下该项风险有限。

### 验证

- `py_compile` 过（`skills_store.py` / `routers/skills.py` / `hub/skillhub_client.py`）。
- **App/Hub 口径一致性**：14 条用例逐条比对两侧 `valid_slug`，判定全等且符合预期（含
  `../../evil` `..` `a/b` `a\b` `--dir` `--dir=/tmp/evil` `a b` `a;rm -rf /` `%2e%2e` `技能` → 全 False；
  `tencent-weiyun__skillhub` `skill-creator` `a.b_c-1` → 全 True）。
- **端到端**（隔离 TestClient 打真路由 + 真 `skills_store`，未重启共享 :8000 以免影响并发会话）：
  9 个攻击 slug × `install`/`preview` **全部 400**，均未触达 CLI；
  合法 slug（`skill-creator` → 200 / `tencent-weiyun__skillhub` → 404）**未被误伤**；
  空 slug + name 仍走 `resolve_slug` 路径未被 400。
- **修复前的对照**已实证漏洞真实：打真 :8000（stale code）时 `../../evil` 原样进了
  `api.skillhub.cn/api/v1/download?slug=../..`，`--dir` 触发了 CLI argparse usage 错误。

### 顺带发现（已另立 issue，未夹带）

验证 `install` 的 name 路径时触发 **WB-187**：`resolve_slug` 无精确命中时「取第一条」，
导致 `{"name":"不存在的技能xyz"}` 真装上了无关的 `self-improving-agent`，
且被 `display_name` 覆盖成用户输入的名字。**该目录已在验证后清理**（`uninstall` 确认，
用户机器恢复为测试前的 6 个技能）。

- commit：未提交（待用户确认）。
