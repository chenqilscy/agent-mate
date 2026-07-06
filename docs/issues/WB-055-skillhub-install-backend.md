---
id: WB-055
title: SkillHub 已安装技能落到后端 + 会话真正挂载（规划）
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - src/stores/skillStore.ts
  - backend/agent/skills.py
created: 2026-07-07
---

## 问题

[[WB-054]] 的 SkillHub 里「安装 / 卸载 / 关闭」目前只落在浏览器 localStorage（`skillStore`），
是纯客户端目录状态：换设备/清缓存即丢，且**并不会让技能在会话里真正生效**——真实挂载仍要
手动在 composer 的 ＋ 菜单里选。安装态与真实能力之间没有打通。

## 触发场景

在 SkillHub 安装一个技能 → 期望它此后能被 agent 使用；实际上后端不知道用户"装了"它，
除非再去 loadout 里手动挂。换台机器登录，已安装列表为空。

## 影响

P2：功能闭环缺一环，但当前客户端持久化已可用、不阻塞浏览；属能力增强而非缺陷。
先登记规划，不在 WB-054 里做。

## 建议修法（待细化）

- 后端建「用户已安装技能」持久化（owner 维度，SQLite），提供 list/install/uninstall/toggle 接口；
  `skillStore` 从 localStorage 迁到调后端 API（参照 `expertStore`/WB-049 的做法）。
- 明确「已安装 / 已关闭」与会话 `loadout.skills` 的关系：已安装且未关闭的技能是否默认进 loadout，
  还是仍需显式挂载；SkillHub 商店的静态目录与真实可执行技能（`backend/agent/skills.py`）如何对应。
- 与 SkillHub CLI（`~/.skillhub`，见项目记忆 skillhub-cli）的关系：是否用 `skillhub install --dir`
  把技能真正装进 workbuddy 的 skills 目录，让"安装"= 真实落盘可用。

## 验证

- 安装后换会话/刷新/换设备，已安装列表一致；已安装技能确实能被 agent 调用（真实工具事件，非模拟）。

## 处理记录（2026-07-07）
- 后端：新增 `agent/skills_store.py`（扫描 `~/.workbuddy/skills/*/SKILL.md`、真实跑
  skillhub CLI `install --dir` 下载解压、uninstall/toggle(.disabled)/detail/reveal、
  search 解析展示名→slug）；`routers/skills.py` 暴露 `/api/skills`（list/search/detail/
  install/{key}/uninstall|toggle|reveal），`main.py` 注册；`config.py` 加 `SKILLS_DIR`/`SKILLHUB_CLI`；
  子进程白名单 env（不透传 LLM_API_KEY，WB-011）。
- 真生效：`agent/skills.py::skill_def` 命中已安装（未停用）磁盘 skill 时注入其真实 SKILL.md 正文。
- 前端：`skillStore` 从 localStorage 改为后端为准（list/install/uninstall/toggle）；`api.ts` 加 skills 方法。
- 验证：模块级 scan/resolve/install/uninstall/inject 全通过；HTTP 在独立 :8001 实例实测
  list/detail/toggle/install(按名解析下载)/uninstall 全 200，真实磁盘目录未残留。`npx tsc --noEmit` 过、`vite build` 过。
- 待办：运行中的 :8000 后端需重启以暴露新路由（reload 未生效，见 CLAUDE.md 已知坑）；live UI 端到端待在应用里点一遍。
- commit：（本提交）
