---
id: WB-161
title: 权威现状文档纠偏 —— CLAUDE.md/README/实现方案 对「Hub 已建成 / auth 已真 / LLM key 入库 / CSS 非 Modules / Tauri 已接」的错误陈述
severity: P2
area: misc
status: fixed
origin: 既有实现
files:
  - CLAUDE.md:45
  - README.md:10
  - docs/workbuddy-实现方案.md:10
created: 2026-07-14
---

## 问题

三份**权威现状文档**已落后于 WB-013~152 的实现，多处对现状的错误陈述（设计稿类 hub/助理/buddywebmgr 的陈旧引用属「设计意图快照」，可接受，不在本 issue 范围）：

1. **`CLAUDE.md:45`**：「当前 auth 是桩、路由尚未按 owner 过滤（见 WB-013）」——实际 M7 已真 Bearer 鉴权、files 等已按 owner/成员过滤、WB-013=fixed；与同文件 line 15「M7 真账户已完成」自相矛盾。
2. **`CLAUDE.md:29`（铁律#4）**：「LLM API Key 只存 `backend/.env`」——实际 WB-124/128/136 各厂商 key 已按 owner 存 DB（`db.get_provider_key`/`routers/models.py`），WB-136 标题即「彻底不读 .env」。应改为「.env 或本机 DB」。
3. **`CLAUDE.md:46`**：「Tauri 待接」——实际 `src/platform/index.ts` 已有完整 `tauriPlatform`，与同文件 line 13「Tauri 已落地」矛盾。
4. **`README.md:10/45`**：状态冻结在 M4；SSE 事件清单（136-138）列了不存在的 `session` builder、漏了 `qa_summary`/`work_item`。
5. **`docs/workbuddy-实现方案.md`**：多处把「独立 Cloud Hub」列为未做/后续（10/45/79/289），实际 `hub/` 已建成运行（与 CLAUDE.md 相反）；决策表/§4 说「CSS Modules / *.module.css」，实际零 module.css、只有 `src/styles/{tokens,app}.css`。

## 影响

P2：误导后续会话（尤其 CLAUDE.md 的 auth/key 断言会让人误判安全边界）。不改代码，只正现状陈述。

## 建议修法

- `CLAUDE.md`：#4 铁律改「LLM key 存 backend/.env 或本机 DB（按 owner），绝不进前端/子进程」；多用户段落改「auth 已真、files 等已按 owner/成员过滤（WB-013 fixed）」；平台段落去掉「Tauri 待接」。
- `README.md`：状态更到当前（M0–M7 + Hub + Manager + 设置中心 + 知识库 + 多助理等）；SSE 事件清单对齐 `events.py`（去 `session`，补 `qa_summary`/`work_item`）。
- `docs/workbuddy-实现方案.md`：把「独立 Cloud Hub 未做」更正为已建成（指向 `hub/` 与 WB-058~063）；「CSS Modules」更正为单一全局 `src/styles/{tokens,app}.css`。

## 验证

- 通读改动段落，与 `hub/`、`src/platform/index.ts`、`backend/agent/events.py`、`src/styles/` 逐一对齐。
- issue 台账镜像同步。

## 处理记录（2026-07-14）

- 改动：
  - `CLAUDE.md`：铁律#4 改「LLM key 存 backend/.env **或按 owner 本机 DB**（WB-124/128/136），都不进前端/子进程」；「多用户」段改「M7 真 Bearer 鉴权、路由已按 owner/成员过滤（WB-013 fixed）、Viewer 只读，共享后端隔离见 WB-153」；「平台抽象」去掉「Tauri 待接」改为已接（`src/platform/index.ts` tauriPlatform）。
  - `README.md`：状态段改「M0–M7 + Hub + Manager 全部落地，逐条以 docs/issues 台账为准」并保留 M0–M4 历史说明；「Later milestones」一行更正；SSE 事件清单补 `qa_summary`/`work_item`、注明 `artifact` 为预留未 yield。
  - `docs/workbuddy-实现方案.md`：进度条下加「⚠️ 现状勘误（2026-07-14，WB-161）」，更正「独立 Cloud Hub 已建成（hub/，WB-058~063）」「样式非 CSS Modules，是单一全局 src/styles/{tokens,app}.css」「LLM key 不再只存 .env」——不逐处重写散落旧文（低风险，用勘误块统一指向现状）。
- 验证：改动段落与 `hub/main.py`·`hub/config.py`、`src/platform/index.ts`、`backend/agent/events.py`（qa_summary:58 / work_item:67 / 无 session builder但有 events.sse('session')）、`src/styles/`（无 *.module.css）逐一核对一致。
- 说明：设计稿类文档（hub/助理/buddywebmgr 的陈旧引用）属「设计意图快照」，本次不动（见 issue 范围）。
- commit：未提交（待用户确认）。
