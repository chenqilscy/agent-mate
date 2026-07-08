---
id: WB-095
title: BuddyWebMgr 设置页 —— 保存 SkillHub API key（Hub 服务端存储 + 注入取数）
severity: P3
area: fullstack
status: fixed
origin: 用户要求
files:
  - hub/db.py
  - hub/routers/settings.py
  - hub/skillhub_client.py
  - hub/web/console.html
created: 2026-07-08
---

## 问题

SkillHub 的 API key（`skh_` 个人 / `sk-ent-` 企业）目前只能靠环境变量配，门户里没有管理入口。用户要一个**设置**功能保存它。

## 触发场景

平台管理员想在 BuddyWebMgr 里填一次 SkillHub API key，之后取数（含 paid/企业私有 registry 等需鉴权的部分）自动带上。

## 影响

P3：把凭据管理搬进门户。读公开目录本不需要 key（见 WB-094）；key 供 paid showcase / 企业 registry / 未来发布用。

## 建议修法

- **Hub `settings` 表**（k-v）+ DAO（get/set/delete）。存 `skillhub_api_key`（服务端 SQLite，`hub.db` gitignored）。
- **`routers/settings.py`（平台管理员）**：GET 返回**打码**状态（`{configured, hint:"skh_1e6e…1251"}`，**不回传全 key**，铁律#4）；PUT 设值；DELETE 清除。
- **`skillhub_client`** 读库里的 key（env 兜底）：HTTP 取数带 `Authorization: Bearer`（解锁 paid/企业）；CLI 兜底时注入其自身 env（`SKILLHUB_TOKEN`/`SKILLHUB_API_KEY`，仅给 SkillHub 子进程，不透传 os.environ）。
- **console**：加「设置」导航（仅管理员）+ SkillHub API key 输入（显示已配置/打码，保存/清除）。

## 验证

设置页填 key → GET 显示已配置+打码 → skillhub_client 取数带上 Bearer（paid showcase 出数）→ 清除后回到未配置；全 key 不回传前端、不入库以外任何文件。

## 处理记录（2026-07-08）

- `hub/db.py`：`settings` 表（k/v/updated_at）+ `get/set/delete_setting`。
- `hub/routers/settings.py`（平台管理员）：`GET /api/settings`（打码 `{configured,hint,kind}`，**不回传全 key**）/ `PUT /api/settings/skillhub-key` / `DELETE`。`main.py` 挂载（别名避与 `config.settings` 撞名）。
- `hub/skillhub_client.py`：`_stored_key()`（库设置优先、env 兜底）；`_cli_env` 注入（`skh_`→`SKILLHUB_TOKEN` / `sk-ent-`→`SKILLHUB_API_KEY`，仅给 SkillHub 子进程）；HTTP 取数带 Bearer。
- `hub/web/console.html`：加「设置」导航（仅管理员）+ SkillHub API Key 卡（已配置/打码/kind、保存、清除）。
- **验证**：Playwright alice(admin) 设置页 → PUT 存 `skh_…` → GET 显「已配置 · `skh_1e6e…1251` · community」（打码）；后端实测 set/mask/clear + 取数注入 key。**用户给的 key 只落 Hub SQLite（gitignored），不回传前端、不提交。**
