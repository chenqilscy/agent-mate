import { useState } from 'react'
import { Space } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { LoginModal } from '../components/auth/LoginModal'
import { WbButton } from '../components/ui/Primitives'
import { openServerConsole } from '../lib/console'
import type { ViewId } from '../lib/types'
import { useAuthStore } from '../stores/authStore'
import { useConnectivityStore } from '../stores/connectivityStore'
import { toast } from '../stores/toastStore'
import { useUIStore } from '../stores/uiStore'

const LOCAL_SHORTCUTS: [ViewId, string, string, string][] = [
  ['skills', '✨', '已安装技能', '管理这台设备可执行的技能'],
  ['connectors', '🔗', '本机连接器', '管理本机 MCP、连接器和凭据'],
]

function serverLabel(state: 'unknown' | 'online' | 'offline' | 'cached'): string {
  if (state === 'online') return '在线'
  if (state === 'cached') return '离线缓存'
  if (state === 'offline') return '离线'
  return '检查中'
}

function statusTone(healthy: boolean | null): string {
  if (healthy === null) return ''
  return healthy ? 'is-in_progress' : 'is-blocked'
}

export function HomeView() {
  const setView = useUIStore((state) => state.setView)
  const setSettingsOpen = useUIStore((state) => state.setSettingsOpen)
  const loggedIn = useAuthStore((state) => state.loggedIn)
  const server = useConnectivityStore((state) => state.server)
  const localAgent = useConnectivityStore((state) => state.localAgent)
  const localAgentChecked = useConnectivityStore((state) => state.localAgentChecked)
  const localAgentError = useConnectivityStore((state) => state.localAgentError)
  const refreshConnectivity = useConnectivityStore((state) => state.refresh)
  const [loginOpen, setLoginOpen] = useState(false)
  const workingCopies = localAgent
    ? Object.values(localAgent.transport.working_copies).reduce((total, count) => total + (count || 0), 0)
    : 0

  const openWorkspace = async () => {
    try {
      await openServerConsole('/')
    } catch {
      toast('无法打开 Server Workspace，请检查 Server 地址和连接状态')
    }
  }

  return (
    <section className="view active" data-view="home">
      <div className="home-wrap">
        <div className="home-inner">
          <div className="home-page-head">
            <div className="home-page-copy">
              <b>Desktop Companion</b>
              <span>这台设备上的 Agent 执行、可信授权、文件与能力控制</span>
            </div>
            <Space size={8} wrap>
              <WbButton className="btn-ghost" onClick={() => void openWorkspace()}>打开 Server Workspace</WbButton>
              <div className={`reward ${localAgentChecked && !localAgent ? 'is-offline' : ''}`} role="status">
                <span className="ri">{localAgent ? '●' : '○'}</span>
                {localAgentChecked ? (localAgent ? 'Local Agent 在线' : 'Local Agent 离线') : '正在检查 Local Agent…'}
              </div>
            </Space>
          </div>

          <div className="home-layout home-workbench-layout">
            <main className="home-workbench-main">
              {!loggedIn && (
                <ProCard className="home-work-card home-login-card" styles={{ body: { display: 'contents' } }}>
                  <div className="home-login-copy"><b>绑定 Server 身份以领取 Run</b><span>业务任务与 Run 由 Server 创建和保存；Desktop Companion 负责这台设备上的授权与执行。</span></div>
                  <WbButton className="btn-dark" onClick={() => setLoginOpen(true)}>登录 Server</WbButton>
                </ProCard>
              )}

              <ProCard className="home-work-card" styles={{ body: { display: 'contents' } }}>
                <div className="home-card-head">
                  <div><b>执行节点状态</b><span>全部来自 Local Agent 与 Server 的实时探测，不使用业务缓存冒充在线</span></div>
                  <WbButton className="home-refresh" onClick={() => void refreshConnectivity()}>刷新状态</WbButton>
                </div>
                {(localAgentError || server.error) && (
                  <div className="home-data-warning" role="status">
                    <span>{localAgentError || server.error}</span>
                    <WbButton className="home-data-warning-action" onClick={() => void refreshConnectivity()}>重新检查</WbButton>
                  </div>
                )}
                <div className="home-run-filters" role="group" aria-label="执行节点状态">
                  <WbButton onClick={() => void refreshConnectivity()}><b>{localAgentChecked ? (localAgent ? '在线' : '离线') : '…'}</b><span>Local Agent</span></WbButton>
                  <WbButton onClick={() => void openWorkspace()}><b>{serverLabel(server.state)}</b><span>Server</span></WbButton>
                  <WbButton onClick={() => setSettingsOpen(true, 'diagnostics')}><b>{localAgent?.transport.leases.active ?? '—'}</b><span>活动租约</span></WbButton>
                  <WbButton onClick={() => setSettingsOpen(true, 'diagnostics')}><b>{localAgent?.transport.wal.count ?? '—'}</b><span>待回执事件</span></WbButton>
                </div>
                <div className="home-action-list">
                  <div className="home-action-row">
                    <span className={`home-action-signal ${statusTone(localAgent ? true : localAgentChecked ? false : null)}`}>执行服务</span>
                    <span className="home-action-copy"><b>{localAgent ? 'Local Agent Core 已就绪' : localAgentChecked ? 'Local Agent Core 不可用' : '正在探测 Local Agent Core'}</b><small>{localAgent ? `协议 v${localAgent.protocol_version} · 已绑定 ${localAgent.transport.identities} 个身份` : '本机工具、文件和进程操作需要 Local Agent'}</small></span>
                    <WbButton className="home-action-primary" onClick={() => setSettingsOpen(true, 'diagnostics')}>执行诊断</WbButton>
                  </div>
                  <div className="home-action-row">
                    <span className={`home-action-signal ${statusTone(server.state === 'unknown' ? null : server.state === 'online')}`}>业务通道</span>
                    <span className="home-action-copy"><b>{server.state === 'online' ? 'Server 业务通道可用' : server.state === 'cached' ? 'Server 离线，仅有缓存' : server.state === 'offline' ? 'Server 业务通道不可用' : '正在探测 Server'}</b><small>项目、任务、Session、Run 和交付以 Server Workspace 为准</small></span>
                    <WbButton className="home-action-primary" onClick={() => void openWorkspace()}>打开 Workspace</WbButton>
                  </div>
                </div>
              </ProCard>

            </main>

            <aside className="home-console home-run-panel" aria-label="本机能力">
              <div className="home-console-head">
                <div><b>本机能力</b><span>只管理这台执行节点拥有的文件、工具、凭据和运行设置</span></div>
                <WbButton className="home-console-action" onClick={() => setSettingsOpen(true, 'runtime')}>运行设置</WbButton>
              </div>
              <div className="home-run-list">
                {LOCAL_SHORTCUTS.map(([view, icon, label, description]) => (
                  <WbButton className="home-run" key={view} onClick={() => setView(view)}>
                    <span className="home-run-dot running" />
                    <span className="home-run-body"><b>{icon} {label}</b><small>{description}</small></span>
                    <span className="home-run-arrow">›</span>
                  </WbButton>
                ))}
              </div>
              <div className="home-status-empty is-muted">
                <span>i</span>{localAgent ? `本机 working copy ${workingCopies} 个 · 执行错误 ${localAgent.transport.errors.length} 条` : 'Local Agent 离线时，本机能力不可用'}
              </div>
            </aside>
          </div>
        </div>
      </div>
      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </section>
  )
}
