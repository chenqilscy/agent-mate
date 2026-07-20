---
id: WB-221
title: 专家定义与推荐位未由 Server 管理且 App 缺少本地人格映射
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

专家页面仍直接展示旧 `EXP_GRID` 橱窗数据，Server 没有可供 App 本地执行的人格定义与独立推荐位。Console 改动专家卡片只影响展示快照，无法保证 agent 真正注入相同 persona。

## 触发场景

在 Console 调整专家信息或人格后打开 App「专家」页面并召唤：App 仍显示旧静态卡片，运行时继续使用本机 builtin persona，Server 配置没有生效。

## 影响

专家运营目录和实际 agent 人格相互脱节；若继续使用展示名关联，重命名会造成 loadout 与运行时映射断裂。

## 建议修法

1. Server 建立稳定 slug 的专家真定义和独立推荐位，推荐位只引用定义。
2. App pull 后把定义映射到本机 `catalog_experts(scope='server')`，运行时优先使用 Server persona。
3. 专家页消费解析后的推荐数据；Console 分开管理专家定义与推荐位。
4. 自定义专家、用户知识与私有配置继续只存 App 本机。

## 验证

- Server API 可管理专家定义和推荐位，并拒绝无效/悬空引用。
- App pull 后专家卡片与运行时 persona 同源；Server 不可达时回退 builtin。
- 推荐位禁用、排期和空配置语义正确，自定义专家不受影响。
- 前后端检查、测试、生产构建与明暗主题浏览器验收通过。

## 处理记录（2026-07-21）

- Server 新增 13 条带稳定 slug、展示资料和真 persona 的 `EXPERT_DEFS`，并将其中 7 条配置为独立 `EXPERT_RECOMMENDATIONS`；API 校验重复、悬空引用与排期并保护被引用定义。
- App pull 将定义写入本机 `catalog_experts(scope='server')`，运行时 persona 优先 Server、离线回退 builtin；本机 `experts` 自定义专家表不参与替换。
- 专家页改为消费生效推荐对象；Console 专家目录使用真定义对象并增加 persona 编辑与推荐位管理，专家团维持原有独立目录。
- 验证：Server 9/9、App 目录 11/11 测试通过，`py_compile`、`npx tsc --noEmit`、`npx vite build`、`git diff --check` 通过。
- 真实 API：临时专家下行后定义数 14、推荐可见且运行时 persona 命中 Server；清理后恢复 13 条定义与 7 条推荐。
- 浏览器：App 明暗主题均显示 7 张专家卡且无横向溢出；Console 显示 13 条定义与 7 条推荐位、无脚本错误；验证后恢复深色主题并清理临时账号。
- commit：本次自动提交。
