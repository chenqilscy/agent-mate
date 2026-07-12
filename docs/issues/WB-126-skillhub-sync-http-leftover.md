---
id: WB-126
title: SkillHub 同步 HTTP 化后的收尾 —— 前端文案仍写「跑 CLI」+ 后台定期同步被 cli_available 卡住
severity: P2
area: fullstack
status: fixed
origin: 既有实现（WB-094 把取数改 HTTP 后未同步收尾）
files:
  - hub/web/console.html:1617
  - hub/main.py:38
created: 2026-07-12
---

## 问题

WB-094 已把 SkillHub 取数从 CLI 子进程改为**优先直连 HTTP**（`rankings_all()` 先 `_http_rankings()`，
失败才回退 `_cli_rankings()`；见 [hub/skillhub_client.py:145](../../hub/skillhub_client.py#L145)）。
但两处收尾没跟上，导致「看起来还在走 CLI」的误导与实际漏洞：

1. **前端文案误导**：手动同步按钮点击时写死提示 `同步中…（跑 CLI，稍候）`
   （[hub/web/console.html:1617](../../hub/web/console.html#L1617)），实际主路径是公开 HTTP 直连、无需 CLI/无需 key。
   用户据此误以为「还在用 CLI 同步、应该改成 API key」——纯显示与实态不符。

2. **后台定期同步被 CLI 存在性卡住**：
   [hub/main.py:38](../../hub/main.py#L38) 的 `if settings.SKILLHUB_SYNC_INTERVAL > 0 and skillhub_client.cli_available()`
   仍用 `cli_available()` 作为启动定期同步的前置条件。手动同步走 HTTP 不受此限，但**后台定期镜像同步**
   在**没有安装 `~/.skillhub` CLI 的环境**下一次都不会启动——而 HTTP 路径本可独立工作。这是实际漏网（部署不可移植）。

（背景：读 SkillHub 公开目录本就无需 API key；key 仅解锁 paid/企业私有 registry，见 WB-094/WB-095。所以「用 key 同步」是误解。）

## 触发场景

- 文案：门户「技能」→ SkillHub 同步子视图点「手动同步」，提示显示「跑 CLI」，但网络请求实际打 `api.skillhub.cn` 公开 HTTP。
- gate：在未装 skillhub CLI 的机器上启动 Hub → 后台定期同步任务因 `cli_available()==False` 不创建 → 目录镜像永不自动刷新（只能靠人工点同步）。

## 影响

P2：#1 纯误导性文案，无功能损失但直接造成用户困惑；#2 有实际影响——无 CLI 环境定期同步失效。两者同源，一起收尾。

## 建议修法

- **console.html**：把 `同步中…（跑 CLI，稍候）` 改为不再声称走 CLI 的中性文案，如 `同步中…（直连 SkillHub，稍候）`。
- **main.py:38**：去掉 `and skillhub_client.cli_available()` 前置——只要 `SKILLHUB_SYNC_INTERVAL > 0` 就启动定期同步；
  HTTP 为主路径、CLI 仅兜底，二者都不可用时 `rankings_all()` 已能优雅返回（showcase 全空抛异常→CLI 返回 `[]`→本轮 upsert 0 条），不会崩。

## 验证

- 前端：点手动同步，提示文案不再出现「CLI」字样；`npx tsc --noEmit` 无关（纯 vanilla console.html，肉眼/浏览器核对）。
- 后端：在 `SKILLHUB_CLI` 指向不存在路径（模拟无 CLI）+ `SKILLHUB_SYNC_INTERVAL>0` 下启动 Hub，确认后台定期同步任务被创建且首轮 HTTP 取数入库（`inserted>0`）；`py_compile hub/main.py` 过。

## 处理记录（2026-07-12）

- 改动：
  - **发现更深根因** —— 除了 issue 原列的 main.py gate，`hub/skillhub_sync.py:57` 的 `sync_once()` 也硬性 `if not cli_available(): return {"...CLI 未安装..."}`，导致无 CLI 环境**连手动同步都被拦**（只改 main.py 无效）。一并去掉该前置，让 `rankings_all()`（HTTP 主、CLI 兜底）驱动；抓空时 `if not cards` 已优雅保留上次镜像。
  - `hub/main.py`：lifespan 去掉 `and skillhub_client.cli_available()` 前置，只判 `SKILLHUB_SYNC_INTERVAL > 0`；`skillhub_client` 变未用导入，一并删。
  - `hub/web/console.html`：4 处「走/跑 CLI」文案改诚实 —— 手动同步提示 `跑 CLI，稍候`→`直连 SkillHub，稍候`；SkillHub 搜索框 + 技能搜索框 placeholder `实时，走 CLI`→`实时，直连`；1 处代码注释同步更新。
- 验证：
  - `SKILLHUB_CLI=/nonexistent` + 隔离 `HUB_DB` 跑 `sync_once()`：`cli_available()==False`，仍 `ok=True`、经 HTTP `total=339`、`inserted=340`（339 技能 + 1 分类骨架行）。改前此路径返回「skillhub CLI 未安装」。
  - `py_compile hub/{main,skillhub_sync,skillhub_client}.py` 全过；前端为 vanilla 模板串纯文本替换，肉眼核对。
- commit：`7c6a403`
