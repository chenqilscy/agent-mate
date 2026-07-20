---
id: WB-169
title: Manager 知识库模板编辑器 —— 新增「向量维度」联动下拉 + 切片方式改下拉 + 切片字数条件显示
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - hub/web/console.html:1596
  - hub/web/console.html:1644
  - hub/web/console.html:1667
  - hub/web/console.html:1691
created: 2026-07-14
---

## 问题

AgentMate Manager 控制台「知识库模板」编辑器（`hub/web/console.html` 的 `knowledgeManage`，
category `KB_TPLS`）有三处可改进（用户反馈，对照编辑器截图）：

1. **缺少「向量维度」配置**。当前只有「向量模型」下拉（`kb-emb`），没有向量维度的展示/选择。
   用户希望以**下拉框**呈现，且语义上「一旦有文件保存进知识库，向量维度就不能再更改」。
2. **「切片方式 knowledge_type」是裸数字输入框**（`kb-kt` `type="number"`），只有一句
   「5=自定义切片」的提示，用户不知道还有哪些合法取值，易填错。应改为**下拉框**。
3. Manager 定位澄清：Manager **只维护模板元数据、不调模型算向量**（铁律#4：无智谱 key、
   不建真库）。这一条现状已满足；本 issue 不给 Manager 加任何真库/文档/向量计算。

### 关键约束（决定第 1 条怎么落地）
GLM 建库接口（`POST /knowledge`，见 `backend/agent/glm_kb.py:create_kb`）**只吃
`embedding_id`（模型），没有任何独立的向量维度参数**——维度完全由 embedding 模型决定
（Embedding-2=1024，Embedding-3 / Embedding-3-pro=2048）。且 App 端建库后模型不可改
（`src/views/KnowledgeView.tsx` 的 `CreateKbModal` 只在建库时设 `embedding_id`，无编辑流），
所以「有文件后维度锁定」天然成立。故**独立可改的维度下拉会喂给一个 GLM 不消费的字段 =
假配置（触铁律#1）**；正确做法是**维度下拉与向量模型联动、只列该模型真实产出的维度**。
（GLM 切片方式真实枚举：1 按标题段落切 / 2 按问答对切片 / 3 按行切片 / 5 自定义切片 /
6 按页切片 / 7 按单个切片；仅 5 用 `sentence_size` 20–2000。）

## 触发场景

打开 Manager（`hub/web/console.html`）→ 目录 → 知识库 → 目录管理 → 编辑/新增模板：
- 看不到「向量维度」；
- 「切片方式」是数字框，输入 4 或 99 等非法值也不拦；
- 「切片字数」始终显示，即便切片方式并非 5（自定义切片）时它其实无意义。

## 影响

P2 择机修：不影响正确性（模板元数据仍能存），但可用性差、易误配；且「向量维度」缺失是
用户明确诉求。纯 Manager 前端展示层。

## 建议修法

**范围仅 `hub/web/console.html`，不动后端/App/catalog.ts。** 数据真源是 `embedding_id`，
向量维度全程由它派生，不新增可漂移的独立存储字段。

1. 在 `KB_EMBEDDINGS`（约 1596 行）旁加两张常量表：
   - `KB_EMB_DIMS = {3:[1024], 11:[2048], 12:[2048]}` + `kbDim(eid)` 取该模型维度；
   - `KB_KTYPES = {1:"按标题段落切",2:"按问答对切片",3:"按行切片",5:"自定义切片",6:"按页切片",7:"按单个切片"}`。
2. `knowledgeManage` 表单（约 1667 行）：
   - 「向量模型」旁新增「向量维度」`<select id="kb-dim">`，由所选模型联动填充（选模型 →
     重建维度选项并选中），muted 提示「跟随模型 · 建库后锁定」；
   - 「切片方式」`kb-kt` 由 number 改 `<select>`，选项来自 `KB_KTYPES`；
   - 「切片字数」`kb-ss` 包一层 `kb-ss-wrap`，仅当切片方式 = 5 时显示（onchange 切换）。
3. `fill()`/`save()`：fill 时同步维度与切片字数显隐；save 时可选把 `embedding_dim=kbDim(...)`
   写进 data（派生镜像，便于消费方展示，永不漂移），`knowledge_type` 取自 select。
4. 详情浮层 `knowledgeDetail`（约 1644 行）「建库参数」行补「维度」并把切片方式显示为
   `值=中文标签`；列表 pill 可附「· N维」。维度显示一律用 `kbDim(embedding_id)` 派生。

## 验证

- Manager 隔离实例（Hub :8100 或 scratchpad 隔离 DB）打开知识库目录管理：
  - 切换向量模型 → 向量维度下拉随之变（Embedding-2→1024，Embedding-3/pro→2048）；
  - 切片方式为下拉、六个真实选项；选 5 才出现切片字数、选其它则隐藏；
  - 保存后重进编辑，维度/切片方式/字数回填正确；
  - 详情浮层与列表显示维度、切片方式中文标签。
- 明暗双主题各看一眼（复用既有 field/select/muted class，不新增写死色）。
- 纯 vanilla 前端，无 tsc；如动到 catalog.ts 才需 `npx tsc --noEmit`（本 issue 不动）。

## 处理记录（2026-07-14）

- **改动**（仅 `hub/web/console.html`，范围收敛，未动后端/App/catalog.ts）：
  - 新增模块级常量 `KB_EMB_DIMS = {3:[1024],11:[2048],12:[2048]}` + `kbDim(eid)` 与
    `KB_KTYPES`（GLM 切片方式真实枚举 1/2/3/5/6/7）。
  - `knowledgeManage` 表单：向量模型旁加「向量维度」`<select id="kb-dim">`（`syncDim` 跟随
    模型联动、muted 提示「跟随模型 · 建库后锁定」）；「切片方式」由 number 改 `<select>`
    （选项来自 `KB_KTYPES`，**默认选中 5=自定义切片**，保持 WB-142 安全默认，避免 GLM
    「文档损坏」）；「切片字数」包 `#kb-ss-wrap`，`syncSs` 仅在切片方式=5 时显示。
  - `fill()` 回填后调 `syncDim/syncSs`；首次渲染即调一次；`save()` 存派生镜像
    `embedding_dim=kbDim(eid)`。
  - 详情浮层 `knowledgeDetail` 建库参数行补「· N 维」并把切片方式显示为「值=中文标签」；
    列表 pill 附「· N维」。维度显示一律 `kbDim(embedding_id)` 派生（不信可能漂移的存储值）。
- **验证**：Hub :8100（serves console.html 逐请求即时生效）+ 独立 headless chromium 走 CDP
  自驱（MCP 浏览器被并发会话占用，用 `cdp-screenshot-when-mcp-browser-locked` 技法），
  以真实 admin(alice) token 进「知识库 → 目录管理」：
  - 三个控件都是 SELECT；切片方式 6 个真实选项带中文标签；
  - 向量维度默认 2048（模型 11）；切模型 Embedding-2→1024 / Embedding-3-pro→2048 / Embedding-3→2048；
  - 切片字数在 kt=5 显示、kt=1 隐藏、回 5 再显示；
  - 详情浮层：`向量模型：Embedding-3 · 2048 维　切片：5=自定义切片 · 300 字/段　上下文增强：关`；
  - **真点保存**新建模板 → 落库 `embedding_id=12, embedding_dim=2048, knowledge_type=6,
    sentence_size=300`（切片方式取下拉真值、非默认）→ 随后 DELETE 清理，不污染共享 Hub。
  - 截图核对暗色主题布局正常（控制台单暗色主题，无 body.dark 切换）；复用既有 field/select/muted
    class，无写死色、无白底白字。
- **commit**：未提交（用户未要求）。

