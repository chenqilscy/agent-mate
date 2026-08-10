import { platform } from '../../platform'
import { useConnectivityStore } from '../../stores/connectivityStore'

const EXPECTED_PROTOCOL_VERSION = 1

function cachedLabel(value: number | null): string {
  if (!value) return ''
  return new Date(value).toLocaleString([], { hour: '2-digit', minute: '2-digit' })
}

export function ConnectivityBanner() {
  const server = useConnectivityStore((state) => state.server)
  const agent = useConnectivityStore((state) => state.localAgent)
  const agentChecked = useConnectivityStore((state) => state.localAgentChecked)
  const messages: string[] = []

  if (server.state === 'cached') {
    messages.push(`Server 离线 · 正在只读显示 ${cachedLabel(server.cachedAt)} 的缓存，修改不会提交`)
  } else if (server.state === 'offline') {
    messages.push('Server 离线 · 当前不能读取新数据或提交修改')
  }

  if (platform.isDesktop && agentChecked && !agent) {
    messages.push('Local Agent 离线 · 本机执行、文件与设备操作不可用')
  } else if (agent && agent.protocol_version !== EXPECTED_PROTOCOL_VERSION) {
    messages.push(`Local Agent 协议不兼容 · 需要 v${EXPECTED_PROTOCOL_VERSION}，当前 v${agent.protocol_version}`)
  }

  const pending = agent?.transport.wal.count ?? 0
  if (pending > 0) {
    messages.push(`Local Agent：${pending} 条执行事件待 Server 回执（无需用户确认）`)
  }

  if (!messages.length) return null
  return <div className="channel-status" role="status">{messages.join('　·　')}</div>
}
