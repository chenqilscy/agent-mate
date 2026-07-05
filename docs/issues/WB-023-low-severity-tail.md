---
id: WB-023
title: 低危备忘集合（12 项）
severity: P3
area: misc
status: open
origin: mixed
files:
  - 见各条
created: 2026-07-06
---

## 说明
一组低危 / 边角 / 设计既定项，集中备忘。处理时可逐条勾掉；若某条升级为需专门跟踪，抽出为独立 WB 编号。

## 清单

- [ ] **ChatSearch 漏跨文本节点匹配** — `ChatSearch.tsx:23` `indexOf` 仅在单个 text node 内查找；markdown 把 `**bold**`/代码/链接切成多节点，跨边界短语搜不到（浏览器原生查找能命中）。属已知取舍，至少文案说明或后续做跨节点合并。
- [ ] **重名附件被静默丢弃却仍提示「已添加」** — `Composer.tsx:68` + `loadoutStore.ts:49` `addRef` 按 `name` 去重；两个不同目录同名文件第二个被丢弃但仍 toast「已添加」。按完整路径/内容去重，或去重时提示。
- [ ] **plan + ask 叠加产生自相矛盾的系统提示** — `runtime.py:163` plan 提示要求用 update_plan/ask_user，ask 后缀又要求「不要调用任何工具」，且 `tools_list=[]` 使 plan 能力全失。行为上 ask 压过 plan，但提示词冲突。显式互斥或定义优先级文案。
- [ ] **plan 模式静默丢弃连接器且横幅不显示** — `runtime.py:226` `if active_connectors and not plan and not ask` 使 plan 下连接器（含只读 list_notes）全不加载，且「已加载」横幅不展示用户已选连接器，易误解。
- [ ] **resolve_model 用 rsplit(":",1)** — `runtime.py:89` 形如 `vendor/model:free` 的真实模型 id 会被误拆成 `free`。当前仅内置标签用 `Display:id`，属边角。
- [ ] **session 事件到达前点停止，后端任务不被停** — `chatStore.ts:225` `api.stopChat` 受 `if(activeId)` 保护；新草稿在 `session` 事件回来前 `activeId` 为 null，此时停止只 abort 客户端连接。拿到 session 后补发 stop，或依赖断开让后端感知。
- [ ] **files usage 每次全量 rglob** — `files.py:129` 每次 `rglob("*")` 全量遍历并在线程池同步阻塞，大工作区慢。可缓存/增量。
- [x] **files.py `root` 死参** — `files.py:76` 的 `root` 参数永远被 `current_root()` 覆盖，属死代码，清理。
- [x] **mcp_stack 在 try 之外打开** — `runtime.py:226` 连接器已 spawn 后、进入 try（`:260`）前有 `yield`（loadout `:258`）；若此窗口内断开或 `mcp_schema` 抛错，`finally` 不执行 → 连接器进程泄漏。纳入同一 try 或用独立 `async with`。
- [x] **ask_user 对畸形模型输出不健壮** — `runtime.py:344` 若模型把 `questions` 返回成字符串列表，`q.get(...)` 抛 `AttributeError`，整轮以「执行出错」中止。对每个 question 做类型校验/跳过。
- [ ] **stop 时 httpx 连接靠 GC 关** — `runtime.py:267` stop `break` 出 `async for` 后，`stream_chat` 内 `httpx.AsyncClient` 不即时关闭。用 `contextlib.aclosing`。
- [ ] **`--text-3`(#9AA0A6) 二级文字对比偏低**（约 2.5:1 on 白）— 占位符/时间戳/空态大量使用，低于 WCAG AA。属逐字迁移的设计 token，若要合规需整体上调。

## 验证
逐条勾除；升级项抽出独立 issue。

## 处理记录（2026-07-06）
- 已勾除 3 项：mcp_stack 纳入 run_chat 主 try（随 WB-012 重构，断开不再泄漏连接器）；ask_user 对畸形 questions（裸字符串）做类型兜底，不再整轮 AttributeError；files.py `/tree` 删除死参 `root`。
- 其余项保持 open：多为设计取舍（跨文本节点搜索、--text-3 对比、plan/ask 提示词优先级）或性能/健壮性备忘（files usage 全量 rglob、stop 时 httpx 靠 GC 关、resolve_model rsplit 边角）；本条作为活备忘保留，升级项再抽独立 WB 编号。
