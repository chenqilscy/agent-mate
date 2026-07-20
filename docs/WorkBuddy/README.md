# 腾讯 WorkBuddy 参考资料

本目录集中保存 AgentMate 产品设计与实现过程中使用的腾讯 WorkBuddy 参考资料。它只用于
**产品结构、交互模式、能力边界和视觉验收**，不表示 AgentMate 与腾讯 WorkBuddy 存在隶属、授权
或品牌关系；AgentMate 是独立产品。

## 资料导航

| 文件 | 用途 | 更新方式 |
|---|---|---|
| [tencent-workbuddy-reference.html](tencent-workbuddy-reference.html) | 早期高保真单页参考原型；用于布局、CSS class、设计 token 和交互路径对照 | 本地静态快照，不随官网自动变化 |
| [official-sources.md](official-sources.md) | 腾讯官网/腾讯云官方文档索引，含访问日期和事实摘要 | 重要设计决策前重新访问原链接核对 |
| [product-design-analysis.md](product-design-analysis.md) | WorkBuddy 产品结构、核心流程和 AgentMate 对标分析 | 随产品路线或官方资料变化维护 |

仓库旧路径 `docs/tencent-workbuddy-reference.html` 保留了兼容跳转，但新文档和代码注释应优先引用
本目录中的真实文件。

## 使用原则

1. **事实与判断分开**：官方明确描述的能力记录在 `official-sources.md`；架构推断和 AgentMate
   取舍记录在 `product-design-analysis.md`，不得把推断写成腾讯官方实现事实。
2. **动态信息标日期**：支持模型、Skill 数量、连接器、渠道、价格和套餐随时可能变化，引用时必须
   带访问日期并在需要时重新核对。
3. **不整页复制官方内容**：本目录保留链接、必要的事实摘要和少量短语义摘录；不镜像受版权保护的
   官方网页全文、图片和视频。
4. **不照搬实现**：参考 WorkBuddy 的产品分层与交互闭环，但 AgentMate 保持 local-first、凭据不出
   本机、工作区文件不上云和真实能力不造假的铁律。
5. **以可验收结果为准**：卡片、名称或提示词不代表能力已经存在；AgentMate 文档只有在工具、运行时、
   产物和验证链路真实可用时，才能标记“已完成”。

## 与 AgentMate 文档的关系

- 总体产品与工程路线：[../agentmate-实现方案.md](../agentmate-实现方案.md)
- Server 控制面与本地执行面：[../agentmate-server-架构设计.md](../agentmate-server-架构设计.md)
- App/Server 数据归属与同步：[../agentmate-数据分层与同步规范.md](../agentmate-数据分层与同步规范.md)
- Console 运营与发布：[../agentmate-console-管理门户设计.md](../agentmate-console-管理门户设计.md)
- 桌面构建与升级：[../desktop-build.md](../desktop-build.md)
- 本轮文档收敛记录：[../issues/WB-235-capability-release-docs-workbuddy-reference.md](../issues/WB-235-capability-release-docs-workbuddy-reference.md)
