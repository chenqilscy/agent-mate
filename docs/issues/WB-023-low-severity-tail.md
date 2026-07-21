---
id: WB-023
title: 低危备忘集合（13 项）
severity: P3
area: misc
status: in-progress
origin: mixed
files:
  - 见各条
created: 2026-07-06
---

## 说明
一组低危 / 边角 / 设计既定项，集中备忘。处理时可逐条勾掉；若某条升级为需专门跟踪，抽出为独立 WB 编号。

## 清单

- [x] **ChatSearch 漏跨文本节点匹配** — 已拆分并修复为 WB-281；搜索在单条消息内合并文本并映射回跨节点 Range，不跨消息拼接。
- [x] **重名附件被静默丢弃却仍提示「已添加」** — 已拆分并修复为 WB-271；同名不同内容可并存，完全重复会得到明确反馈，chip 按内部 ID 独立删除。
- [x] **plan + ask 叠加产生自相矛盾的系统提示** — 已拆分并修复为 WB-272；前端互斥，后端对冲突请求按 Ask 优先归一。
- [x] **plan 模式静默丢弃连接器且横幅不显示** — 已拆分并修复为 WB-273；仍保守禁用外部 MCP，但轨迹逐项说明连接器因计划模式未加载。
- [x] **resolve_model 用 rsplit(":",1)** — 已拆分并修复为 WB-274；旧显示标签只切首个冒号，裸 `vendor/model:free` 整体保留。
- [ ] **session 事件到达前点停止，后端任务不被停** — `chatStore.ts:225` `api.stopChat` 受 `if(activeId)` 保护；新草稿在 `session` 事件回来前 `activeId` 为 null，此时停止只 abort 客户端连接。拿到 session 后补发 stop，或依赖断开让后端感知。
- [ ] **files usage 每次全量 rglob** — `files.py:129` 每次 `rglob("*")` 全量遍历并在线程池同步阻塞，大工作区慢。可缓存/增量。
- [x] **files.py `root` 死参** — `files.py:76` 的 `root` 参数永远被 `current_root()` 覆盖，属死代码，清理。
- [x] **mcp_stack 在 try 之外打开** — `runtime.py:226` 连接器已 spawn 后、进入 try（`:260`）前有 `yield`（loadout `:258`）；若此窗口内断开或 `mcp_schema` 抛错，`finally` 不执行 → 连接器进程泄漏。纳入同一 try 或用独立 `async with`。
- [x] **ask_user 对畸形模型输出不健壮** — `runtime.py:344` 若模型把 `questions` 返回成字符串列表，`q.get(...)` 抛 `AttributeError`，整轮以「执行出错」中止。对每个 question 做类型校验/跳过。
- [ ] **stop 时 httpx 连接靠 GC 关** — `runtime.py:267` stop `break` 出 `async for` 后，`stream_chat` 内 `httpx.AsyncClient` 不即时关闭。用 `contextlib.aclosing`。
- [ ] **`--text-3`(#9AA0A6) 二级文字对比偏低**（约 2.5:1 on 白）— 占位符/时间戳/空态大量使用，低于 WCAG AA。属逐字迁移的设计 token，若要合规需整体上调。
- [x] **首页「更多」快捷入口 chip 是占位 toast** — `HomeView.tsx:50` 场景 quick chips 末项 `⋯ 更多` 点击仅 `toast('更多快捷入口')`，无展开面板/目标视图（原型 `tencent-agentmate-reference.html:1423` 亦如此；`catalog.ts:5` 每场景仅 3 项 + 更多，无「更多」数据源）。与同屏其它占位 toast（`打开成长计划`:28 / `选择工作空间`:79 / `默认权限`:84）同类。若要落地需补完整 quick-entry 数据 + 展开 UI；否则属设计既定占位，至少可让文案更明确（如「敬请期待」）。

## 验证
逐条勾除；升级项抽出独立 issue。

## 处理记录（2026-07-06）
- 已勾除 3 项：mcp_stack 纳入 run_chat 主 try（随 WB-012 重构，断开不再泄漏连接器）；ask_user 对畸形 questions（裸字符串）做类型兜底，不再整轮 AttributeError；files.py `/tree` 删除死参 `root`。
- 其余项保持 open：多为设计取舍（跨文本节点搜索、--text-3 对比、plan/ask 提示词优先级）或性能/健壮性备忘（files usage 全量 rglob、stop 时 httpx 靠 GC 关、resolve_model rsplit 边角）；本条作为活备忘保留，升级项再抽独立 WB 编号。

## 处理记录（2026-07-06，追加）
- 新增第 13 项并同日勾除：首页「更多」快捷入口 chip 文案由 `更多快捷入口` 改为 `更多快捷入口，敬请期待`，明确其为未实现占位（用户确认「保持占位」，最小改动）。改动：`src/views/HomeView.tsx:50`。同屏其余占位 toast（打开成长计划/选择工作空间/默认权限）与原型 `tencent-agentmate-reference.html:1423` 未动。
- 验证：`npx tsc --noEmit` 通过；纯 toast 文案改动，无 CSS/token 变更，不涉主题翻转。
