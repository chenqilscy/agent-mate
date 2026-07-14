---
id: WB-172
title: Manager 项目「知识库」tab —— 真·建库(向量维度/切片方式下拉)+文档上传/列/删+维度锁
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - hub/web/console.html
created: 2026-07-14
---

## 问题

配套 [[WB-171]] 后端，Manager 控制台需在**项目详情**里加「知识库」tab，做真·知识库+文档管理的 UI：
建库时配**向量维度**（下拉，有文档后锁）+**切片方式**（下拉）；**上传/列/删文档**（真字节，经 WB-171）；
文档状态**诚实**标「未向量化·待执行面处理」，**绝不显示「已向量化」**（铁律#1）。Manager 不算向量。

## 触发场景

Manager 进项目 → 只有 概览/任务/协作/配置 四个 tab，无处管理真知识库。

## 影响

P2：纯前端 console.html。项目级、按项目角色（Viewer 只读）。暗色单主题。

## 建议修法

**范围仅 `hub/web/console.html`，新前缀 `kbm-`（防并发撞车）。**

1. **项目详情加「知识库」tab**：`PD_TAB` 增 `knowledge`；`projectDetail`（:473-478）加 `pdTabBtn("knowledge","知识库")`；
   `pdRenderTab`（:484-491）加分支 → `kbmView(body, PD.pid, PD.ro)`。
2. **建库表单**：复用 `.card/.field/.grid2`；向量模型+向量维度联动下拉（复用 WB-169 已在文件里的
   `KB_EMBEDDINGS/KB_EMB_DIMS/kbDim`+`syncDim`）；切片方式下拉（复用 `KB_KTYPES`，sentence_size 仅 5 显示）。
3. **库列表**：照 `usersView`（:1104-1222）reload/render/空态/错误脚手架 + `.list-item` 行（打开/编辑/删）。
4. **库详情**（右侧抽屉照 `pmOpenTask` :984-1066，或子面板）：库配置（编辑时**有文档则向量模型/维度 select 加
   `disabled`**——锁）+ 文档区：上传（新 `apiUpload` 助手）、列表带诚实状态 pill（未向量化·待执行面处理 / ✗失败）、删。
   `PD.ro`（Viewer）隐藏写操作。建/删确认复用 `expModal/expClose`（:1256-1267）。
5. **新 `apiUpload(path, file)` 助手**（现有 `api()` 仅 JSON，:304-313）：`fetch(...+"?filename="+enc(file.name),
   {method:"POST", headers:{Authorization:Bearer}, body:file})`——发原始字节（配后端 stream，免 multipart），错误照 `api()`。

## 验证

- `node` 提取 `<script>` 做 `new Function()` 语法检查（纯 vanilla，无 tsc）。
- 隔离 Hub + 独立 headless Chromium CDP 自驱（MCP 浏览器常被并发占用）：进项目→知识库 tab→建库（选维度/切片下拉、
  切模型看维度联动）→传 .txt→文档出现且状态「未向量化」（非已向量化）→再编辑库维度 select 已 disabled→删文档→删库；
  暗色截图核对复用既有 class 无破样式。

## 处理记录（2026-07-14）

- **改动**（仅 `hub/web/console.html`，`kbm-` 前缀）：
  - 新 `apiUpload(path, file)` 助手（现有 `api()` 只发 JSON）：发原始文件字节 + filename 走 query，配 WB-171 后端。
  - `projectDetail` 加「知识库」tab（`PD_TAB` 增 `knowledge`、`pdTabBtn`、`pdRenderTab` 分支 → `kbmRender`）；
    进项目重置 `KBM_OPEN=null`。
  - `kbmList`：建库表单（向量模型+向量维度联动下拉 / 切片方式下拉 / 切片字数仅 5 显示 / 上下文增强 / 标签，
    复用 WB-169 的 `KB_EMBEDDINGS/KB_EMB_DIMS/KB_KTYPES`）+ 库列表（emb·dim维·N文档 pill，打开/删除）。
  - `kbmDetail`：库配置编辑（**有文档时向量模型/维度 select disabled + 「已有文档·锁定」+ 头部「维度已锁」**）+
    文档区（真上传经 apiUpload、列表带**诚实状态 pill**「未向量化·待执行面处理」/「✗失败」，**绝不显示已向量化**、删除）。
    Viewer（`PD.ro`）隐藏所有写操作。
- **验证**：`node` 提取 `<script>` `new Function()` 语法过（147k 字符）。隔离 Hub :8109 + 独立 headless Chromium
  CDP 自驱（kbtester 登录）实测：进项目→知识库 tab→建库（切模型 Embedding-2 → 向量维度联动 1024、切片方式下拉
  1/2/3/5/6/7）→列表出现「CDP测试库 Embedding-2·1024维 0文档」→打开（向量模型可改）→**经隐藏 file input 真上传
  cdp-doc.txt**→文档列表出现「cdp-doc.txt 未向量化·待执行面处理」（**非**已向量化）→**向量模型 select 变 disabled +
  头部「维度已锁」+「已有文档·锁定」**。暗色截图核对布局正常、复用既有 class 无破样式。
- **commit**：未提交（待用户要求）。
