---
id: WB-246
title: Skill 下行缺少 tombstone、客户端能力报告与增量兼容门禁
severity: P0
area: fullstack
status: open
origin: 既有实现
files:
  - server/routers/catalog.py:42
  - backend/server_sync.py:113
  - backend/storage/db.py:2072
  - shared/skill-tools.json:1
created: 2026-07-21
---

## 问题

Server 普通目录下行省略停用的 `APP_SKILLS`，App 全量替换 Server scope 后可能重新暴露同 slug builtin，
所以中心停用不能可靠撤回能力。工具契约虽声明 `min_app_version`，但 App 没有上报版本/支持工具，
下行与安装均未执行兼容门禁；同步也没有目录 revision、条件请求与 last-known-good 状态协议。

## 触发场景

- Console 归档一个随 App 打包的 builtin Skill，App pull 后该 slug 从 Server scope 消失并回退 builtin。
- 新 Server 为 Skill 绑定旧 App 不支持的工具，旧 App 只能在运行时过滤，运营侧看不到不兼容设备。
- 长时间运行的 App 不重新登录，无法及时获得撤回或安全更新。

## 影响

P0：紧急撤回失效；不兼容能力可以被展示或安装；离线、网络失败和中心撤回语义混淆。

## 建议修法

- 下行显式携带 active/withdrawn tombstone，App 持久化并压制相同 slug builtin。
- 增加目录 revision/ETag 与条件 pull；不可达时保留 last-known-good，不把空响应当撤回。
- App 上报 `app_version`、平台、架构、tool contract 和 supported tools；Server 返回兼容结论。
- 浏览可以展示不兼容说明，但安装、升级和运行必须硬门禁。

## 验证

- Server 停用 builtin 同 slug Skill 后，App 不再回退出该能力；恢复发布可重新启用。
- 旧 App 对高版本工具显示最低版本要求，安装与运行均被拒绝。
- 同 revision 条件请求不重复改写本地目录；断网继续使用最后可用状态。
