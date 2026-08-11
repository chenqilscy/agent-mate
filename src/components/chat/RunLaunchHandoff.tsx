import { openServerConsole } from '../../lib/console'
import { toast } from '../../stores/toastStore'
import { WbButton } from '../ui/Primitives'

export function RunLaunchHandoff({ projectId }: { projectId?: string }) {
  const openWorkspace = async () => {
    try {
      await openServerConsole(projectId ? `/projects/${projectId}` : '/')
    } catch {
      toast('无法打开 Server Workspace，请检查 Server 地址和连接状态')
    }
  }

  return (
    <div className="pe-readonly run-launch-handoff" role="status">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M8 12h8M12 8v8" /><circle cx="12" cy="12" r="9" /></svg>
      <span className="run-launch-handoff-copy">
        <b>新的 Run 从 Server Workspace 发起</b>
        <small>Desktop Companion 继续负责这台节点上的授权、执行观察与工件。</small>
      </span>
      <WbButton className="btn-line" onClick={() => void openWorkspace()}>打开 Workspace</WbButton>
    </div>
  )
}
