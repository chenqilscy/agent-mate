import { Alert, Result } from 'antd'
import { WbButton } from '../components/ui/Primitives'
import { openServerConsole } from '../lib/console'
import { useUIStore } from '../stores/uiStore'

const COPY = {
  assistant: ['助理与渠道', '助理定义、发布和渠道治理属于 Server 控制平面。'],
  automation: ['自动化管理', '自动化定义、触发策略、重试和审计由 Server 统一调度。'],
  experts: ['专家目录', '共享专家与能力目录由 Server 统一发布；Desktop Companion 只选择已安装能力执行任务。'],
  projects: ['项目与任务', '项目、任务上下文、Run 发起和交付验收属于 Server Workspace。'],
  project: ['项目管理', '项目计划、成员、风险和协作记录由 Server Console 维护。'],
} as const

export function ConsoleHandoffView() {
  const view = useUIStore((state) => state.view)
  const entry = COPY[view as keyof typeof COPY] || COPY.project
  return (
    <section className="view active">
      <div className="page-scroll">
        <Alert
          type="info"
          showIcon
          title="这是 Server Workspace / Console 的职责"
          description="Desktop Companion 只保留本机执行、可信授权、文件、凭据和诊断，不复制 Server 的业务页面。"
        />
        <Result
          status="info"
          title={entry[0]}
          subTitle={entry[1]}
          extra={<WbButton className="btn-dark" onClick={() => void openServerConsole()}>打开 Server Workspace</WbButton>}
        />
      </div>
    </section>
  )
}
