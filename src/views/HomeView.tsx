import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { Space } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { LoginModal } from '../components/auth/LoginModal'
import { Composer } from '../components/composer/Composer'
import { PermPopover } from '../components/composer/PermPopover'
import { Popover } from '../components/ui/Popover'
import { WbButton } from '../components/ui/Primitives'
import { openServerConsole } from '../lib/console'
import type { ViewId } from '../lib/types'
import { useAuthStore } from '../stores/authStore'
import { useCatalog } from '../stores/catalogStore'
import { useChatStore } from '../stores/chatStore'
import { useConnectivityStore } from '../stores/connectivityStore'
import { useProjectStore } from '../stores/projectStore'
import { useSettingsStore } from '../stores/settingsStore'
import { toast } from '../stores/toastStore'
import { useUIStore } from '../stores/uiStore'

const LOCAL_SHORTCUTS: [ViewId, string, string, string][] = [
  ['skills', '✨', '已安装技能', '管理这台设备可执行的技能'],
  ['connectors', '🔗', '本机连接器', '管理本机 MCP、连接器和凭据'],
  ['myfiles', '📁', '本机文件', '查看 Local Agent 工作区与交付文件'],
  ['projects', '☁️', '任务上下文', '从 Server 选择要在本机执行的任务'],
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
  const startDraft = useChatStore((state) => state.startDraft)
  const startProject = useChatStore((state) => state.startProject)
  const send = useChatStore((state) => state.send)
  const setView = useUIStore((state) => state.setView)
  const setSettingsOpen = useUIStore((state) => state.setSettingsOpen)
  const loggedIn = useAuthStore((state) => state.loggedIn)
  const server = useConnectivityStore((state) => state.server)
  const localAgent = useConnectivityStore((state) => state.localAgent)
  const localAgentChecked = useConnectivityStore((state) => state.localAgentChecked)
  const localAgentError = useConnectivityStore((state) => state.localAgentError)
  const refreshConnectivity = useConnectivityStore((state) => state.refresh)
  const projects = useProjectStore((state) => state.projects)
  const loadProjects = useProjectStore((state) => state.load)
  const perm = useSettingsStore((state) => state.perm)
  const { QUICK } = useCatalog()

  const [loginOpen, setLoginOpen] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [popover, setPopover] = useState<'workspace' | 'permission' | null>(null)
  const [moreOpen, setMoreOpen] = useState(false)
  const [keyboardNavigation, setKeyboardNavigation] = useState(false)
  const workspaceAnchor = useRef<HTMLButtonElement | null>(null)
  const permissionAnchor = useRef<HTMLButtonElement | null>(null)
  const moreAnchor = useRef<HTMLElement | null>(null)

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Tab') setKeyboardNavigation(true) }
    const onPointerDown = () => setKeyboardNavigation(false)
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [])

  const selectedProject = selectedProjectId
    ? projects.find((project) => project.id === selectedProjectId)
    : null
  const promptSuggestions = (QUICK.day || []).filter(([, label]) => label !== '更多').slice(0, 3)
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

  const launch = (text: string) => {
    if (!loggedIn) {
      setLoginOpen(true)
      toast('请先登录 Server，Local Agent 才能领取任务')
      return
    }
    if (!localAgent) {
      toast('Local Agent 离线，暂时不能开始本机执行')
      return
    }
    const title = text.length > 26 ? `${text.slice(0, 26)}…` : text
    if (selectedProject) startProject(selectedProject.id, title)
    else startDraft(title)
    setView('chat')
    void send(text)
  }

  const openMore = (event: MouseEvent<HTMLElement>) => {
    moreAnchor.current = event.currentTarget
    setMoreOpen(true)
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
                  <div className="home-login-copy"><b>绑定 Server 身份后开始执行</b><span>业务任务与 Run 由 Server 保存；Desktop Companion 只把授权后的工作交给这台 Local Agent。</span></div>
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
                    <WbButton onClick={() => void refreshConnectivity()}>重新检查</WbButton>
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

              <ProCard className={`home-command home-quick-start ${keyboardNavigation ? 'is-keyboard-navigation' : ''}`} styles={{ body: { display: 'contents' } }}>
                <div className="home-card-head"><div><b>发起本机执行</b><span>过渡期保留执行入口；任务治理、行动项和交付验收已迁往 Server Workspace</span></div></div>
                <div className="comp-zone">
                  <Composer variant="home" onSend={launch} autoFocus />
                  <div className="ctray">
                    <WbButton className="tray-chip" ref={workspaceAnchor} onClick={() => setPopover((current) => current === 'workspace' ? null : 'workspace')}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>{selectedProject?.name ?? '选择任务上下文'}
                    </WbButton>
                    <WbButton className="tray-chip" ref={permissionAnchor} onClick={() => setPopover((current) => current === 'permission' ? null : 'permission')}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>{perm}
                    </WbButton>
                  </div>
                  <Popover open={popover === 'workspace'} anchor={workspaceAnchor.current} dir="down" onClose={() => setPopover(null)} minWidth={220}>
                    <div className="pop-item" onClick={() => { setSelectedProjectId(null); setPopover(null) }}>无（默认空间）{selectedProjectId === null && <span className="chk">✓</span>}</div>
                    {projects.length === 0 && <div className="pop-item pop-empty">暂无 Server 项目上下文</div>}
                    {projects.map((project) => <div className="pop-item" key={project.id} onClick={() => { setSelectedProjectId(project.id); setPopover(null) }}><span className="pi-ic">🗂️</span>{project.name}{selectedProjectId === project.id && <span className="chk">✓</span>}</div>)}
                  </Popover>
                  <Popover open={popover === 'permission'} anchor={permissionAnchor.current} dir="down" onClose={() => setPopover(null)} className="perm-pop" minWidth={232}><PermPopover /></Popover>
                </div>
                <div className="home-prompt-suggestions" aria-label="执行建议">
                  {promptSuggestions.map(([icon, label]) => <WbButton className="qchip" key={label} onClick={() => launch(label)}>{icon} {label}</WbButton>)}
                  <WbButton className="qchip" aria-haspopup="menu" aria-expanded={moreOpen} onClick={openMore}>⋯ 本机能力</WbButton>
                </div>
                <Popover open={moreOpen} anchor={moreAnchor.current} dir="down" onClose={() => setMoreOpen(false)} className="more-shortcuts" minWidth={248}>
                  <div className="more-shortcuts-head">本机能力</div>
                  {LOCAL_SHORTCUTS.map(([view, icon, label, description]) => <WbButton key={view} role="menuitem" className="pop-item more-shortcut-item" onClick={() => { setMoreOpen(false); setView(view) }}><span className="more-shortcut-icon">{icon}</span><span className="more-shortcut-copy"><b>{label}</b><small>{description}</small></span><span className="more-shortcut-arrow">›</span></WbButton>)}
                </Popover>
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
