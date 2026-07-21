---
id: WB-151
title: GLM 知识库 WB-141 审查修复 —— 轮询闭包/无扩展名/key 前置/空 body/形状守卫
severity: P2
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - src/views/KnowledgeView.tsx
  - backend/routers/knowledge.py
  - backend/agent/glm_kb.py
created: 2026-07-14
---

## 问题

WB-141 落地后代码复审（独立 review agent + 自审）发现 5 处缺陷：

- **H1（高·核心 UX 失效）** `KnowledgeView.tsx:74`：向量化状态轮询 `setInterval` 回调闭包捕获 `openId`（state，列表视图渲染时恒为 null）而非 `id`（参数）→ `if (openId)` 恒假，每 4s 空转不刷新。打开一个「已在向量化」的库时状态永远卡「⏳ 向量化中…」；且死 interval 占了 `poll.current` 让后续正确闭包也被 `!poll.current` 挡掉。「建空库→上传」路径能工作故未被 curl 测试暴露。
- **M2** `knowledge.py:119`：`"README".rsplit(".",1)` → `["README"]`，`ext="readme"` 非空且不在白名单 → 无扩展名文件被误拒「不支持的文件类型:.readme」（拖拽绕过前端 accept）。
- **M3** `glm_kb.py:41`：`_unwrap` 对 2xx 空 body / 204 会 `r.json()` 抛错误判失败（DELETE/PUT）。实测 GLM delete 返回信封故当前不触发，但应防御。
- **M4** `knowledge.py:110`：上传先把整个 body（≤50MB）灌进内存才查 key，没配 key 的用户白缓冲。`_key()` 应在读 body 前调。
- **L1** `KnowledgeView.tsx:125`：capacity 无形状守卫，GLM 返回缺 `total/used` 时 `.length` 抛 TypeError 白屏。

## 建议修法

- H1：interval 回调改用 `id` 参数 `() => void refreshDocs(id)`。
- M2：扩展名守卫改 `if ("." in filename)` 再取 ext。
- M3：`_unwrap` 对 2xx 且空 body / 204 直接返回 None（成功）。
- M4：`upload_document` 开头先 `key = _key()`，再流式读 body。
- L1：capacity 读取加可选链 / 数值兜底。

## 验证

`npx tsc --noEmit`；`py_compile knowledge.py glm_kb.py`；真机：上传无扩展名文件报友好错、打开在向量化的库能自动刷新状态、没配 key 上传即时 400 不缓冲。

## 处理记录（2026-07-14）

- 改动：H1（interval 用 id 参数）+ L1（capUsed/capTotal/capWords 可选链兜底）于 KnowledgeView.tsx；M2（`"." in filename` 守卫）+ M4（`key=_key()` 前置于流式读 body）于 knowledge.py；M3（`_unwrap` 2xx 空 body → None）于 glm_kb.py。
- 验证：`npx tsc --noEmit` 过、`py_compile`+import 过。硬重启 :8000 真机验 M2 三态：无扩展名 `noext` 过我方校验→GLM 自身拒「不支持的文档类型」（不再是我方误报 `.noext`）、`.exe` 我方拒、`.md` 成功。M4/M3 逻辑核实（M3 GLM delete 实返信封故原本不触发，加防御）；H1/L1 前端 tsc 过、修法即 review 定位的根因。
- commit：`edf6f31`（`fix(WB-151): GLM 知识库 WB-141 审查修复`）。

## 关闭复核（2026-07-22）

- 历史修复提交、处理记录与 README 的 ✅ 状态一致，frontmatter 原先遗留的
  `in-progress` 已纠正为 `fixed`。
- 后续知识库执行面已由 GLM 迁移至 WeKnora；仍适用的轮询闭包修复和无扩展名判断已保留在
  当前实现中，已移除的 GLM 客户端不再作为现行运行时依赖。
