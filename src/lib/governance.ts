import type { RiskSeverity, WorkItem, WorkPriority } from './types'

export const RISK_DESCRIPTION_TEMPLATE = `## 触发条件

描述什么情况出现时，这项风险会发生。

## 潜在影响

描述可能造成的业务、交付、成本或安全影响。

## 影响范围

- 受影响的用户、系统或团队：
- 受影响的里程碑或目标：

## 关闭条件

- [ ] 处置任务已通过真实交付验收
- [ ] 关键验证结果符合预期
- [ ] 残余风险已评估并记录

## 残余风险

风险关闭前补充仍然存在的限制、监控项或复查时间。
`

const PRIORITY_TO_SEVERITY: Record<WorkPriority, RiskSeverity> = {
  '': 'medium',
  low: 'low',
  medium: 'medium',
  high: 'high',
  urgent: 'critical',
}

export function riskSeverityForWorkItem(priority: WorkPriority): RiskSeverity {
  return PRIORITY_TO_SEVERITY[priority]
}

export function riskDescriptionForWorkItem(item: WorkItem): string {
  const context = item.description.trim() || `关联任务：${item.title}`
  return `${RISK_DESCRIPTION_TEMPLATE.trim()}\n\n## 任务上下文\n\n${context}\n`
}

export function decisionDescriptionForWorkItem(item: WorkItem): string {
  const context = item.description.trim() || `关联任务：${item.title}`
  return `任务上下文：\n${context}\n\n待决策事项：\n\n决策影响：\n`
}
