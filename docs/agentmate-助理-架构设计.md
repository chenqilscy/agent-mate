# AgentMate 助理（多助理 · 多渠道）架构设计

> 面向 epic **WB-086**。把现有「单助理」（WB-072 桥接 / WB-077 设置面板）泛化为一套
> **多助理 + 多渠道** 子系统：可建多个助理，每个助理有独立能力配置与独立的多个外部渠道。
> 本文是权威蓝图；实现按 §7 分片推进，逐片一个子 issue。

## 1. 背景与现状

- **WB-072**：Telegram 长轮询桥接——一个 bot、白名单/`/start` 配对、驱动真实 `run_chat`。
- **WB-077**：助理设置面板——单助理的 名字/人格/模型/开关/token(存 DB)/解绑。
- 现有数据：`assistant_settings`（单行，owner 级）、`channel_sessions`（chat↔会话）、`channel_state`（轮询游标）。

局限：**只有一个助理、一个渠道、一套配置**。本设计将其泛化。

## 2. 目标（用户诉求）

1. 支持配置**多个渠道**。
2. 支持添加**多个助理**，每个助理可设置**独立的（多个）渠道**。
3. **每种渠道的配置因类型而不同**（Telegram：bot token + 配对；其它类型各异）。
4. 每个助理可**独立设置**：指令 · 技能 · 连接器 · 专家 · 大模型 · 权限 · 工作空间。
5. 完善的 UI。

### 2.1 现实约束（不造假，铁律#1）

- **只有 Telegram 有可用凭据能真跑**。「多渠道」= 多个 Telegram bot + **可扩展的渠道类型结构**；
  其它类型（企业微信/WhatsApp/邮件…）先做成**明确标注「敬请期待」的占位**，不摆不生效的假开关。
- **「权限」映射到已有的真实杠杆**：`run_chat` 的 执行 / 计划(plan) / 问答(ask) 三态
  （后端当前不强制细粒度工具权限；本 epic 不新造权限门，见 §4 决策记录）。

## 3. 核心数据模型

### 3.1 `assistants`（新）

| 字段 | 说明 |
|---|---|
| id / owner_id | 主键 / 归属（local-first：LOCAL_USER；预留多用户） |
| name / avatar | 名字 / emoji 头像 |
| instruction | 指令 / 人格（注入 `run_chat` 的 `system_extra`，复用 WB-077 机制） |
| model | 大模型（空=跟随后端默认） |
| mode | 权限：`exec`(执行,全工具) / `plan`(计划,只读+ask_user) / `ask`(问答,无工具) |
| workspace | 工作空间：`default` / `project:<id>`（复用某项目沙箱）/ `dedicated`（专属 `workspace/assistants/<id>/`） |
| experts / skills / connectors | loadout（JSON 数组；复用现有挑选器 UI 与注入路径） |
| enabled | 助理级开关 |
| created_at / updated_at | |

### 3.2 `channels`（新）

| 字段 | 说明 |
|---|---|
| id / assistant_id | 主键 / 属于哪个助理（一个助理挂 0..N 个渠道） |
| type | 渠道类型：`telegram`（可用）；其它类型登记但标注 unavailable |
| config | **类型相关**的 JSON。`telegram` → `{ bot_token(write-only,存 DB), pairing|allow_chat_ids }` |
| enabled | 渠道级开关 |
| created_at | |

> **渠道类型注册表**（后端常量 + 前端目录）：`{ type, label, available, config_schema }`。
> 决定「新增渠道」时能选哪些类型、每类型渲染什么表单。新增渠道类型 = 加一个适配器 + 一条注册项。

### 3.3 复用/泛化现有表

- `channel_sessions`：`(channel_id, chat_id) → session_id`（原按 `channel='telegram'` 单例，改为按 `channel_id`）。
- `channel_state`：轮询游标改为**按 channel_id**（每个 bot 各自游标）。
- **会话**：**每个助理一条长期会话**（kind=`assistant`，owner 级），其所有渠道 + App 共享它（延续 WB-072 Slice 2 的「共享会话」，键从 owner 改为 assistant）。
- **迁移**：见 §6。

## 4. 决策记录（本次已定）

1. **助理 = 新建独立实体**（非复用 Project）。复用 Project 的 loadout/沙箱**机制与 UI 组件**，但与
   协作（成员/看板）解耦——助理是「外部渠道 agent」，语义独立。
2. **权限 = 映射 Plan/Ask/执行**三态，不新造细粒度工具权限门（后端零新增权限逻辑；`run_chat` 已支持 plan/ask）。
3. **先设计后实现**：本文 + epic 登记先行，逐片实现。

## 5. 运行时

### 5.1 渠道管理器（ChannelManager）

- 取代 WB-072 里单一的全局 `_task`。维护 `{channel_id: poller_task}`。
- `reconcile()`：按 DB 里「启用且类型可用」的渠道集合，启新、停删、换 token 的重启。
  启动时（main.py startup）与任何渠道/助理配置变更后调用。
- 每个 Telegram 渠道 = 一个独立长轮询 loop（各自 token / 游标 / getMe / deleteWebhook）。
  → `telegram_api` 需从「全局 token override」改为**每次调用显式传 token**（多 bot 并存）。

### 5.2 入站消息路由

```
渠道 C 收到消息
  → 鉴权（C.config 的白名单/配对）
  → 助理 A = C.assistant_id
  → ensure A 的会话
  → run_chat(session, user, text,
             model=A.model,
             plan=(A.mode=='plan'), ask=(A.mode=='ask'),
             experts=A.experts, skills=A.skills, connectors=A.connectors,
             system_extra=A.instruction,
             workspace=A.workspace)      # run_chat 新增 workspace 覆盖参数
  → 回复发回 C
```

- `run_chat` 需新增可选 `workspace` 覆盖（当前只按 `session.project_id` 切根）：
  `dedicated`→`workspace/assistants/<id>/`（sandbox 扩展）、`project:<id>`→该项目根、`default`→默认。

## 6. 迁移（非破坏）

新模型初始化时，若检测到 WB-077 的 `assistant_settings` 有数据：
- 建 1 条 `assistants`（名字/人格/模型 从旧行搬），mode 由旧 enabled 推断为 `exec`；
- 建 1 条 `channels`（type=telegram，token/绑定从旧 `assistant_settings.bot_token` + `channel_sessions` 搬）；
- 旧助理会话（owner 级）挂到这条新助理；`channel_sessions` 重指向 channel_id。
- 旧表保留（回退安全），标记已迁移，避免重复迁。

## 7. 分片（子 issue，逐片实现）

| 片 | 子 issue | 领域 | 内容 |
|---|---|---|---|
| **S1** | WB-087 | backend | `assistants`+`channels` 表 + 泛化 `channel_sessions/state` + CRUD API + ChannelManager(多 bot) + `run_chat` 接 workspace/mode + `telegram_api` 改每次传 token + 单助理迁移 |
| **S2** | WB-088 | frontend | 「助理」页重构为 主从视图：助理列表 + 新建 + 设置 tab（指令/模型/权限(Plan/Ask/执行)/工作空间 + 专家·技能·连接器 挑选器）+ 对话 tab（复用 WB-072/085） |
| **S3** | WB-089 | fullstack | 渠道 tab：类型化渠道 CRUD UI（Telegram 表单：token/配对/开关；其它类型「敬请期待」占位）+ 入站路由端到端真机验证（多 bot） |
| **S4** | WB-090 | fullstack | 打磨 + 迁移收尾 + 明暗双主题 + 多 bot 真机验证 + 台账/文档收口 |

> 每片单独一个 commit（标题带对应 WB-###），单独真机验证。S1 会**重构** WB-072/077 的实现
> （单助理成为「一个助理 + 一个渠道」的特例），务必保证迁移后现有 @CkyBuddyBot 仍可用。

## 8. UI 蓝图（S2/S3）

「助理」一级视图 → 主从布局：

- **左：助理列表**——头像 + 名字 + 状态点（🟢连接/🟡未启用/⚪未配渠道）+「＋ 新建助理」。
- **右：选中助理**——三 tab：
  - **对话**：真实 transcript + Composer（从 App 驱动该助理；复用 WB-072/085）。
  - **设置**：名字/头像/指令(textarea)/模型(ModelPicker)/权限(执行·计划·问答)/工作空间(默认·项目·专属)
    + 专家/技能/连接器（复用 `PickerOverlay`）。
  - **渠道**：该助理的渠道列表；「＋ 新增渠道」→ 选类型（Telegram 可用 / 其它占位）→ 类型表单
    （Telegram：token(write-only)/配对状态/解绑/开关）。每条渠道可单独启停/删除。
- 复用既有 `.np-*` 弹窗、`PickerOverlay`、`ModelPicker`、`Popover`；暗色天然继承。

## 9. 安全与铁律

- token 存 DB、write-only、绝不回传前端（延续 WB-077，铁律#4 已同步措辞）。
- 每个渠道单实例轮询（Telegram 同 bot 只允许一个 getUpdates）。
- 白名单/配对按**渠道**独立；助理跑在其**自己的工作空间沙箱**内。
- 不造假：其它渠道类型明确「敬请期待」；权限只暴露真实可用的三态。
