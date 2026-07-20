---
id: WB-220
title: 连接器定义与推荐位未由 Server 管理且 App 缺少本地运行态映射
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - server/catalog_seed.py
  - server/routers/catalog.py
  - backend/server_sync.py
  - backend/storage/db.py
  - src/views/ExpertsView.tsx
created: 2026-07-21
---

## 问题

连接器页面仍直接展示前端静态 `CONNS`，Server 的 `CONN_DEFS` 既没有独立推荐位，也没有在下行后映射到 App 本地 `catalog_connectors`。因此运营目录、页面展示和真实 MCP 运行定义是三套数据，无法保证推荐卡片对应可用连接器。

## 触发场景

在 Console 新增或调整连接器定义后打开 App「连接器」页面：页面仍显示打包时的静态卡片；即使定义已下行，agent 运行时也不会使用 Server 定义。

## 影响

Server 无法运营连接器推荐内容，App 展示与实际能力脱节；继续扩展会积累名称映射和配置漂移技术债务。

## 建议修法

1. Server 建立稳定 slug 的连接器定义和独立推荐位，推荐位只引用定义。
2. App 后端下行定义后写入本机 `catalog_connectors`，运行时优先使用 Server 映射；密钥、OAuth 状态仍只留本机。
3. 前端连接器页消费解析后的推荐数据；Console 分开管理定义与推荐位。
4. 保留 Server 不可达时的本地目录兜底。

## 验证

- Server API 可增删改连接器定义和推荐位，并拒绝无效/悬空引用。
- App pull 后本地运行时可见对应定义，但 Server 数据中不存在密钥值。
- 推荐位禁用、定时未生效、空配置均在 App 正确反映；离线时仍显示本地可用连接器。
- `npx tsc --noEmit`、相关 Python 编译与测试通过；明暗主题页面无回归。

## 处理记录（2026-07-21）

- Server 新增带稳定 slug 的 `CONN_DEFS` 默认定义与独立 `CONNECTOR_RECOMMENDATIONS` 推荐位，支持排序、启停与排期；API 校验悬空/重复引用，并限制 `secret_env` 只能保存环境变量名。
- App pull 将公开定义映射到本机 `catalog_connectors(scope='server')`，MCP 运行时优先 Server 定义、离线自动回退 builtin；token、OAuth 与实际密钥值不下行。
- 连接器页改为消费解析后的生效推荐；Console 拆出浏览橱窗、目录管理和推荐位管理，文档同步更新。
- 验证：Server 7/7、App 目录 9/9 测试通过，`py_compile`、`npx tsc --noEmit`、`npx vite build`、`git diff --check` 通过；真实 API 临时创建/拉取/清理连接器后由 7 条恢复为 6 条。
- 浏览器：App 明暗主题均展示 6 条推荐且无横向溢出；Console 显示 6 条定义和 6 条推荐位，页面无脚本错误；验证后恢复深色主题并清理临时账号。
- commit：本次自动提交。
