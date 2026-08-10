import { WbButton } from '../components/ui/Primitives'
import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { Composer } from '../components/composer/Composer'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { useProjectStore } from '../stores/projectStore'
import { useSettingsStore } from '../stores/settingsStore'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'
import { Popover } from '../components/ui/Popover'
import { PermPopover } from '../components/composer/PermPopover'
import type { SessionInfo } from '../lib/types'
import { Segmented, Space, Statistic } from 'antd'
import { CompatList as List } from '../components/ui/CompatList'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'
import type { ViewId } from '../lib/types'
import { useAuthStore } from '../stores/authStore'
import { useConnectivityStore } from '../stores/connectivityStore'
import { LoginModal } from '../components/auth/LoginModal'

const SCENES: [string, string, string][] = [
  ['day', '🔥', '日常办公'],
  ['code', '💻', '代码开发'],
  ['design', '🎨', '设计创意'],
]

const MORE_SHORTCUTS: [ViewId, string, string, string][] = [
  ['skills', '✨', '已安装技能', '管理这台设备可执行的技能'],
  ['connectors', '🔗', '本机连接器', '配置仅保存在本机的连接凭据'],
  ['myfiles', '📁', '本机文件', '查看 Local Agent 工作区文件'],
  ['projects', '☁️', '项目上下文', '从 Server 选择任务执行上下文'],
]

function runState(session: SessionInfo): { label: string; tone: string } {
  if (session.run_status === 'error') return { label: '自动化失败', tone: 'error' }
  if (session.status === 'waiting') return { label: '等待输入', tone: 'waiting' }
  return { label: '执行中', tone: 'running' }
}

function runSource(session: SessionInfo): string {
  if (session.kind === 'automation') return '自动化 Run'
  if (session.project_id) return '项目 Run'
  return '个人 Run'
}

export function HomeView() {
  const [scene, setScene] = useState('day')
  const startDraft = useChatStore((s) => s.startDraft)
  const startProject = useChatStore((s) => s.startProject)
  const openSession = useChatStore((s) => s.openSession)
  const sessions = useChatStore((s) => s.sessions)
  const loadSessions = useChatStore((s) => s.loadSessions)
  const send = useChatStore((s) => s.send)
  const setView = useUIStore((s) => s.setView)
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen)
  const loggedIn = useAuthStore((s) => s.loggedIn)
  const localAgent = useConnectivityStore((s) => s.localAgent)
  const localAgentChecked = useConnectivityStore((s) => s.localAgentChecked)
  const { QUICK } = useCatalog()
  const [moreOpen, setMoreOpen] = useState(false)
  const moreAnchor = useRef<HTMLElement | null>(null)

  const projects = useProjectStore((s) => s.projects)
  const loadProjects = useProjectStore((s) => s.load)
  const setActiveProject = useProjectStore((s) => s.setActive)
  const perm = useSettingsStore((s) => s.perm)
  const [loginOpen, setLoginOpen] = useState(false)

  // 首页新任务的目标空间（null = 默认空间，不绑定任何项目）与两个 tray popover。
  const [selProject, setSelProject] = useState<string | null>(null)
  const [pop, setPop] = useState<'ws' | 'perm' | null>(null)
  const wsAnchor = useRef<HTMLButtonElement | null>(null)
  const permAnchor = useRef<HTMLButtonElement | null>(null)

  useEffect(() => { void loadProjects(); void loadSessions() }, [loadProjects, loadSessions])

  const activeRuns = useMemo(() => sessions.filter((s) =>
    s.kind !== 'assistant' && (s.status === 'running' || s.status === 'waiting' || s.run_status === 'running'),
  ), [sessions])

  const runningRuns = useMemo(() => sessions.filter((s) =>
    s.kind !== 'assistant' && s.status !== 'waiting' && (s.status === 'running' || s.run_status === 'running'),
  ), [sessions])

  const waitingRuns = useMemo(() => sessions.filter((s) =>
    s.kind !== 'assistant' && s.status === 'waiting',
  ), [sessions])

  const recentFailures = useMemo(() => {
    const since = Date.now() / 1000 - 7 * 86400
    return sessions.filter((s) =>
      s.kind === 'automation' && s.run_status === 'error' && (s.updated_at ?? s.created_at ?? 0) >= since,
    )
  }, [sessions])

  const selName = selProject ? projects.find((p) => p.id === selProject)?.name : null

  const launch = (text: string) => {
    if (!loggedIn) {
      setLoginOpen(true)
      toast('请先登录 Server，Local Agent 才能领取任务')
      return
    }
    const title = text.length > 26 ? text.slice(0, 26) + '…' : text
    if (selProject && selName) startProject(selProject, title)
    else startDraft(title)
    setView('chat')
    void send(text)
  }

  const openRun = async (session: SessionInfo) => {
    if (session.project_id) {
      const project = projects.find((p) => p.id === session.project_id)
      if (project) setActiveProject(project)
    }
    await openSession(session.id)
    setView(session.project_id ? 'projexec' : 'chat', {
      projectId: session.project_id ?? undefined,
      sessionId: session.id,
    })
  }

  const attentionRuns = [...activeRuns, ...recentFailures.filter((failed) => !activeRuns.some((run) => run.id === failed.id))].slice(0, 4)
  const completedRuns = sessions.filter((session) => session.status === 'done').slice(0, 4)
  const failedRuns = recentFailures.length

  const openMore = (event: MouseEvent<HTMLDivElement>) => {
    moreAnchor.current = event.currentTarget
    setMoreOpen(true)
  }

  return (
    <section className="view active" data-view="home">
      <div className="home-wrap">
        <div className="home-inner">
          <div className="home-page-head">
            <div className="home-page-copy">
              <b>个人 Agent 工作台</b>
              <span>组织任务、发起 Run，并监督和验收 Agent 工作</span>
            </div>
            <div
              className={`reward ${localAgentChecked && !localAgent ? 'is-offline' : ''}`}
              role="status"
              title={localAgent ? `${localAgent.transport.identities} 个 Server 身份 · WAL ${localAgent.transport.wal.count}` : undefined}
            >
              <span className="ri">{localAgent ? '●' : '○'}</span>
              {localAgentChecked ? (localAgent ? `Local Agent 在线${localAgent.transport.wal.count > 0 ? ` · ${localAgent.transport.wal.count} 条待同步` : ''}` : 'Local Agent 离线，本机执行暂不可用') : '正在检查 Local Agent…'}
            </div>
          </div>
          <div className="home-layout">
            <div className="home-command">
              <h1 className="hero-title">
                <span className="hero-brand">AgentMate</span>
                <span className="g">你的 Agent 工作台</span>
              </h1>
              <Segmented
                className="scenes"
                value={scene}
                onChange={(value) => setScene(String(value))}
                options={SCENES.map(([value, icon, label]) => ({ value, label: <span className="scene"><span className="si">{icon}</span>{label}</span> }))}
              />
              <div className="quick">
                {QUICK[scene].map(([ic, label]) => (
                  <div
                    key={label}
                    className="qchip"
                    {...clickable}
                    aria-haspopup={label === '更多' ? 'menu' : undefined}
                    aria-expanded={label === '更多' ? moreOpen : undefined}
                    onClick={label === '更多' ? openMore : () => launch(label)}
                  >
                    {ic === '⋯' ? (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="18" cy="12" r="1.6" /></svg>
                    ) : (
                      ic
                    )}{' '}
                    {label}
                  </div>
                ))}
              </div>

              <Popover open={moreOpen} anchor={moreAnchor.current} dir="down" onClose={() => setMoreOpen(false)} className="more-shortcuts" minWidth={248}>
                <div className="more-shortcuts-head">更多能力</div>
                {MORE_SHORTCUTS.map(([view, icon, label, description]) => (
                  <WbButton
                    key={view}
                    type="button"
                    role="menuitem"
                    className="pop-item more-shortcut-item"
                    onClick={() => { setMoreOpen(false); setView(view) }}
                  >
                    <span className="more-shortcut-icon" aria-hidden="true">{icon}</span>
                    <span className="more-shortcut-copy"><b>{label}</b><small>{description}</small></span>
                    <span className="more-shortcut-arrow" aria-hidden="true">›</span>
                  </WbButton>
                ))}
              </Popover>

              <div className="comp-zone">
                {!loggedIn && (
                  <div className="projects-context is-attention">
                    <div className="projects-context-copy">
                      <b>登录 Server 后开始本机执行</b>
                      <span>Server 保存任务和 Run；Local Agent 使用这台设备的模型、技能、凭据和工作区执行。</span>
                    </div>
                    <WbButton className="btn-line" onClick={() => setLoginOpen(true)}>登录 Server</WbButton>
                  </div>
                )}
                <svg className="mascot2" viewBox="0 0 100 100" aria-hidden="true">
                <circle cx="79" cy="13" r="9" fill="#16B37A" />
                <path d="M75 13l3 3 5-5" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" />
                <path d="M24 48a28 20 0 0152 0" fill="none" stroke="#9AA6B2" strokeWidth="5" strokeLinecap="round" />
                <rect x="16" y="44" width="12" height="19" rx="6" fill="#8B98A6" />
                <rect x="72" y="44" width="12" height="19" rx="6" fill="#8B98A6" />
                <path d="M34 38l7 9M66 38l-7 9" stroke="#C7CFD8" strokeWidth="6" strokeLinecap="round" />
                <rect x="29" y="44" width="42" height="40" rx="17" fill="#E2E7ED" />
                <ellipse cx="43" cy="63" rx="4.3" ry="5.6" fill="#16B37A" />
                <ellipse cx="57" cy="63" rx="4.3" ry="5.6" fill="#16B37A" />
                <circle cx="44.5" cy="61" r="1.3" fill="#eafff6" />
                <circle cx="58.5" cy="61" r="1.3" fill="#eafff6" />
                <path d="M46 73q4 2.6 8 0" stroke="#8B98A6" strokeWidth="2.4" fill="none" strokeLinecap="round" />
                </svg>
                <Composer variant="home" onSend={launch} autoFocus />
                <div className="ctray">
                <WbButton
                  className="tray-chip"
                  ref={wsAnchor}
                  onClick={() => setPop((c) => (c === 'ws' ? null : 'ws'))}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
                  {selName ?? '选择工作空间'}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
                </WbButton>
                <WbButton
                  className="tray-chip"
                  ref={permAnchor}
                  onClick={() => setPop((c) => (c === 'perm' ? null : 'perm'))}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 14, height: 14 }}><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
                  {perm}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
                </WbButton>
                </div>
                <Popover open={pop === 'ws'} anchor={wsAnchor.current} dir="down" onClose={() => setPop(null)} minWidth={220}>
                <div className="pop-item" {...clickable} onClick={() => { setSelProject(null); setPop(null) }}>
                  无（默认空间）{selProject === null && <span className="chk">✓</span>}
                </div>
                {projects.length === 0 && <div className="pop-item pop-empty">暂无工作空间</div>}
                {projects.map((p) => (
                  <div className="pop-item" key={p.id} {...clickable} onClick={() => { setSelProject(p.id); setPop(null) }}>
                    <span className="pi-ic">🗂️</span>{p.name}{selProject === p.id && <span className="chk">✓</span>}
                  </div>
                ))}
                </Popover>
                <Popover open={pop === 'perm'} anchor={permAnchor.current} dir="down" onClose={() => setPop(null)} className="perm-pop" minWidth={232}>
                  <PermPopover />
                </Popover>
              </div>
            </div>

            <ProCard className="home-console" aria-label="任务进展" styles={{ body: { display: 'contents' } }}>
              <div className="home-console-head">
                <div>
                  <b>执行概览</b>
                  <span>你的 Run 与待处理事项</span>
                </div>
                <Space size={6}>
                  <WbButton className="home-console-action" onClick={() => setSettingsOpen(true, 'diagnostics')}>执行诊断</WbButton>
                  <WbButton className="home-console-action" onClick={() => setSettingsOpen(true, 'runtime')}>运行设置</WbButton>
                </Space>
              </div>
              <div className="home-metrics">
                <ProCard className="home-metric"><Statistic value={runningRuns.length} title="执行中" /></ProCard>
                <ProCard className="home-metric waiting"><Statistic value={waitingRuns.length} title="等待我确认" /></ProCard>
                <ProCard className={`home-metric ${failedRuns > 0 ? 'danger' : ''}`.trim()}><Statistic value={failedRuns} title="近 7 天失败" /></ProCard>
              </div>
              <div className="home-console-grid">
                <div className="home-run-group">
                  <h2>需要关注</h2>
                  {attentionRuns.length > 0 ? <List dataSource={attentionRuns} renderItem={(session) => {
                    const state = runState(session)
                    return <List.Item className="home-run-item">
                      <WbButton className="home-run" onClick={() => void openRun(session)}>
                        <span className={`home-run-dot ${state.tone}`} />
                        <span className="home-run-body">
                          <b>{session.title}</b>
                          <small>{state.label} · {session.ago ?? '刚刚'}</small>
                        </span>
                        <span className="home-run-arrow">›</span>
                      </WbButton>
                    </List.Item>
                  }} /> : <div className="home-status-empty" role="status"><span aria-hidden="true">✓</span>当前没有需要处理的任务</div>}
                </div>
                <div className="home-run-group">
                  <h2>最近完成</h2>
                  {completedRuns.length > 0 ? <List dataSource={completedRuns} renderItem={(session) => <List.Item className="home-run-item">
                    <WbButton className="home-run" aria-label={`打开${session.title}，${runSource(session)}`} onClick={() => void openRun(session)}>
                      <span className="home-file-icon">✓</span>
                      <span className="home-run-body">
                        <b>{session.title}</b>
                        <small>{runSource(session)} · {session.ago ?? '最近完成'}</small>
                      </span>
                      <span className="home-run-arrow">›</span>
                    </WbButton>
                  </List.Item>} /> : <div className="home-status-empty is-muted">还没有已完成的 Run</div>}
                </div>
              </div>
            </ProCard>
          </div>
        </div>
      </div>
      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </section>
  )
}
