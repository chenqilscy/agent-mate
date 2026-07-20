---
id: WB-238
title: 权威文档残留过时架构、端口与能力边界，且以勘误掩盖正文冲突
severity: P1
area: misc
status: fixed
origin: 🆕 近期改动
files:
  - README.md:12
  - CLAUDE.md:8
  - package.json:16
  - docs/issues/README.md:4
  - docs/agentmate-实现方案.md:8
  - docs/agentmate-server-架构设计.md:3
  - docs/agentmate-数据分层与同步规范.md:3
  - docs/agentmate-console-管理门户设计.md:3
  - docs/agentmate-助理-架构设计.md:1
  - docs/weknora-部署.md:9
created: 2026-07-21
---

## 问题

仓库的实现已经历独立 AgentMate Server、Console、Skill 生命周期、第三方 SkillHub 边界、
多助理多渠道和端口统一等多轮重构，但 README、工作指南和 `docs/` 中仍混有初始蓝图与当前事实：

- `docs/agentmate-实现方案.md` 自称“唯一权威/活文档”，正文却仍写 CSS Modules、认证桩、共享后端、
  M5 才接 Tauri、静态橱窗占位等旧方案，只在顶部追加勘误；同一文件内相互冲突。
- `docs/agentmate-server-架构设计.md` 仍标为“动手前 v1”，把独立 Server、目录入库和同步写成未来目标，
  并把尚未落地的增量 pull、双向同步等蓝图与已实现的全量镜像/时间线元数据 outbox 混写。
- `README.md` 仍称 Server 周期镜像第三方 SkillHub；实际 WB-215 已移除 Server 镜像、代理、Key 和技能包，
  市场浏览/安装由本地 App 直连。
- `CLAUDE.md` 仍引用旧 WorkBuddy 路径，并把已落地的评论、@提及、在线状态和目录 Admin 列为未做。
- Console 与助理架构文档仍以单文件 legacy Console、Telegram 单渠道的实施前语气描述当前系统。
- `package.json` 的 `gen:api` 仍访问已废弃的 `localhost:8000`，与现行 App backend `:8101` 不一致。
- issue 索引仍把 skill 路径写成已经不存在的 `.claude/skills/issue-tracker/SKILL.md`。
- WB-158 索引文件名错误，且若干历史 issue 仍链接已经改名的 Server/Console 架构文档。
- WeKnora 部署文档固化了某台开发机的端口、模型 id、运行状态，并错误声称 Windows backend
  `reload=True`；这些机器态信息既会过期，也不应成为共享部署说明。

## 触发场景

新成员按 README/实现方案启动或理解系统，或运行 `pnpm gen:api`：会得到错误的数据流、组件结构、
能力边界或直接连接错误端口；评审者也无法区分已经实现的事实、历史里程碑与目标设计。

## 影响

P1：这些文件被 README 和工作指南当作入口/权威依据，会直接误导开发、部署、产品规划和能力发布判断；
“正文错误 + 顶部勘误”的维护方式还会让后续修改继续叠加矛盾。

## 建议修法

- 将实现方案重写为当前架构与真实能力基线；历史 M0–M8 排期和选型论证交由 Git 历史与 issue 台账保存。
- 将 Server/Console/助理文档改为“当前实现 + 明确目标”，删掉已完成事项的未来时态和不存在的数据流。
- 统一端口、SkillHub、本地密钥、认证、样式与 WorkBuddy 参考路径表述。
- 修正 OpenAPI 生成端口和 issue-tracker 路径。
- 不改写历史 issue 的验收记录；不删除 `docs/tencent-workbuddy-reference.html` 兼容跳转，因为工作区仍有旧入口引用。
- 不触碰 WB-236/WB-237 的进行中范围，也不纳入未跟踪的 `docs/agentmate-功能规划-v2.md`。

## 验证

- 权威文档不再命中 CSS Modules、共享后端即 Server、Server 周期 SkillHub 镜像、认证桩、旧 `:8000` 等错误现状。
- 所有受控 Markdown 相对链接存在；WorkBuddy 新旧入口均可用。
- `pnpm gen:api` 的 URL 指向 `http://localhost:8101/openapi.json`（不要求为了文档清理启动服务）。
- `git diff --check` 通过，且提交只包含 WB-238 范围，不夹带 WB-236/WB-237 或未跟踪文件。

## 处理记录

- 2026-07-21：将 `agentmate-实现方案.md` 从“当前结论 + 旧里程碑 + 旧 ADR + 顶部勘误”的混合稿
  收敛为当前拓扑、代码边界、真实能力、已知缺口、运行与文档职责；删除正文中的 CSS Modules、
  认证桩、共享后端、静态橱窗和旧 Tauri 排期等冲突描述。
- 重写 Server/Console/助理专项文档：明确 Server 已实现的控制面与当前全量 pull/outbox 边界，
  区分能力发布目标；记录 Console React/Ant Design 迁移期双入口；把 Telegram/邮件标为真实渠道，
  企业微信/WhatsApp 保持不可用。
- README 与 CLAUDE 改为当前三层拓扑、SkillHub 本地直连、真实协作能力和当前待办；修正 WorkBuddy
  路径、issue-tracker 路径和 Windows `reload=False` 规则。
- `package.json` 的 `gen:api` 改为 App backend `:8101`；WeKnora 指南移除某台机器的端口、模型 id、
  Docker 运行状态等瞬时信息；保留通用 `:8080` 示例并注明自定义替换。
- 修复 WB-158 索引文件名，以及 WB-058～063、WB-078 等因架构文档改名产生的断链；历史问题结论、
  旧代码路径和验收环境记录保持不变。
- 精确检查后未删除 `docs/tencent-workbuddy-reference.html`：它是 387-byte 兼容跳转，工作区仍有旧入口
  引用；原型真实文件继续保存在 `docs/WorkBuddy/`。未触碰未跟踪的功能规划稿和 WB-236 并行源码。
- 验证：13 份当前文档的全部本地 Markdown 链接存在；issue 索引所有 WB 文件存在；定向检索未再命中
  当前文档中的旧端口/路径/架构声明；Node 解析 `package.json` 并确认 `gen:api` 使用 `:8101`；
  `git diff --check` 通过。
