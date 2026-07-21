---
id: WB-244
title: 缺少可复用登录态且提交前强制确认的真实浏览器工具
severity: P1
area: backend
status: fixed
origin: WB-239 R1
files:
  - backend/agent/tools.py:1
  - backend/agent/runtime.py:1
  - backend/requirements.txt:1
  - backend/tests/golden/tasks.json:6
created: 2026-07-21
---

## 问题

AgentMate 的“浏览器”目前只是任务页里的展示标签，agent 工具集中没有导航、读取、交互、截图、上传或下载能力。
`web_fetch` 只做无登录态 HTTP GET，`run_command` 启动任意浏览器既不可观察也无法保证提交前确认，不能满足 R1 G05。

## 触发场景

用户要求在已登录网站查询信息、填写表单并在最终提交前让自己确认，或将网页结果截图/下载到当前项目。
模型无法复用登录态，也可能用通用 shell 绕过 trace；失败时没有页面 URL、动作、截图和 Artifact 可追溯。

## 影响

P1：网页任务不可交付，R1 黄金任务缺一条高频真实工具链；直接开放通用浏览器自动化还会引入 SSRF、
本机服务探测、跨 owner cookie 混用、未确认外部写入和下载逃逸等安全风险。

## 建议修法

- 使用 Playwright + 本机已安装 Edge/Chrome，每 owner 隔离持久化 profile，后端不返回 cookie/secret；
- 提供导航/读取与结构化交互工具，动作、最终 URL、标题和可见文本进入真实 trace；
- URL 仅允许 HTTP(S)，默认阻断 localhost、环回、链路本地、私网和非全局 DNS 结果；
- fill/select/check 等本地页面编辑可执行，submit 按钮、Enter 提交和显式 submit 动作必须返回
  `confirmation_required`，在 R2 审批令牌落地前不允许模型自行声明已确认；
- 截图、上传和下载路径必须在当前沙箱，截图/下载登记 Artifact；并发访问同 owner profile 串行化。

## 验证

- 本机 Edge/Chrome 上真实完成公共网页导航、读取、填写；profile 在两次工具调用间复用；
- submit 元素、Enter 和 submit 动作不会触发网络写，工具明确要求用户确认；
- localhost/private/越界 upload/download 路径被拒绝；不同 owner profile 不共享；
- 截图/下载进入 Run Artifact，文件存在且哈希匹配；计划模式仅开放只读导航/读取，不开放交互；
- G05 离线本地测试站与真机公共网页验收通过，sidecar 打包并启动成功。

## 处理记录（2026-07-21）

- 运行时：固定 `playwright 1.61.0`，不下载自带 Chromium；按 Windows 系统路径发现 Edge/Chrome，
  每 owner 使用独立持久 profile，并显式保存/恢复 storage state 解决短生命周期 headless cookie 回放不稳定。
- secret 边界：cookie/storage state 改存 DB 同级 `.browser-profiles`，完全位于 agent workspace 之外并加入
  `.gitignore`；安全复查时发现并删除了仅由本次测试产生的旧 workspace profile（180 文件、约 15 MB）。
- 工具：新增 plan-safe 的 `browser_navigate` / `browser_read`，以及执行 fill/select/check/click/upload/
  screenshot/download 的 `browser_interact`；截图与下载原子落盘并进入 Run Artifact。
- 安全：只允许无内嵌账号密码的 HTTP(S)；默认阻断 localhost、单标签主机、私网、环回、链路本地和
  非全局 DNS，兼容 Clash/Mihomo `198.18/15` 公网域名占位但阻断字面 IP；route 层阻断全部非
  GET/HEAD/OPTIONS 请求。submit 控件、显式 submit 与 Enter 均返回 `confirmation_required` 且不执行。
- 自动验证：本机真实 Edge 对离线测试站完成 cookie 跨调用复用、owner 隔离、fill/upload、submit 阻断、
  screenshot/download 和私网门禁，3/3 通过；全量 regression 58/58、Python compile、TS 类型检查和
  Vite 生产构建通过。
- 真机验收：真实 LLM 调用 `browser_navigate` 打开 `https://example.com` 并生成 15 KB 全页 PNG，
  Artifact 来源/格式/存在性/哈希均正确；PyInstaller 产物约 153 MB，含 174 个 Playwright 模块和
  110 个 driver 条目，打包 sidecar 内再次由真实 LLM 取到 `Example Domain`，最终产物在隔离 `:8193`
  健康启动；所有临时会话、截图、进程与测试目录已清理。
