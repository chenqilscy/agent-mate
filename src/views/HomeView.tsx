import { WbButton } from '../components/ui/Primitives'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { useProjectStore } from '../stores/projectStore'
import { useSettingsStore } from '../stores/settingsStore'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'
import { Popover } from '../components/ui/Popover'
import { PermPopover } from '../components/composer/PermPopover'
import { api, type RawMessage } from '../lib/api'
import type { SessionInfo } from '../lib/types'
import { Empty, Segmented, Spin, Statistic } from 'antd'
import { CompatList as List } from '../components/ui/CompatList'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'

const SCENES: [string, string, string][] = [
  ['day', '🔥', '日常办公'],
  ['code', '💻', '代码开发'],
  ['design', '🎨', '设计创意'],
]

type Delivery = { session: SessionInfo; files: string[] }

function changedFiles(messages: RawMessage[]): string[] {
  const files = new Set<string>()
  for (const message of messages) {
    for (const raw of message.trace) {
      if (!raw || typeof raw !== 'object') continue
      const trace = raw as { kind?: unknown; file?: unknown }
      if (trace.kind === 'diff' && typeof trace.file === 'string') files.add(trace.file)
    }
  }
  return [...files]
}

function fileName(path: string): string {
  return path.replaceAll('\\', '/').split('/').pop() ?? path
}

function runState(session: SessionInfo): { label: string; tone: string } {
  if (session.run_status === 'error') return { label: '自动化失败', tone: 'error' }
  if (session.status === 'waiting') return { label: '等待输入', tone: 'waiting' }
  return { label: '执行中', tone: 'running' }
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
  const { QUICK } = useCatalog()

  const projects = useProjectStore((s) => s.projects)
  const loadProjects = useProjectStore((s) => s.load)
  const setActiveProject = useProjectStore((s) => s.setActive)
  const perm = useSettingsStore((s) => s.perm)
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [deliveriesLoading, setDeliveriesLoading] = useState(true)

  // 首页新任务的目标空间（null = 默认空间，不绑定任何项目）与两个 tray popover。
  const [selProject, setSelProject] = useState<string | null>(null)
  const [pop, setPop] = useState<'ws' | 'perm' | null>(null)
  const wsAnchor = useRef<HTMLButtonElement | null>(null)
  const permAnchor = useRef<HTMLButtonElement | null>(null)

  useEffect(() => { void loadProjects(); void loadSessions() }, [loadProjects, loadSessions])

  const activeRuns = useMemo(() => sessions.filter((s) =>
    s.kind !== 'assistant' && (s.status === 'running' || s.status === 'waiting' || s.run_status === 'running'),
  ), [sessions])

  const recentFailures = useMemo(() => {
    const since = Date.now() / 1000 - 7 * 86400
    return sessions.filter((s) =>
      s.kind === 'automation' && s.run_status === 'error' && (s.updated_at ?? s.created_at ?? 0) >= since,
    )
  }, [sessions])

  useEffect(() => {
    let cancelled = false
    const candidates = sessions
      .filter((s) => s.kind !== 'assistant' && s.status !== 'running' && s.status !== 'waiting')
      .slice(0, 12)

    if (candidates.length === 0) {
      setDeliveries([])
      setDeliveriesLoading(false)
      return () => { cancelled = true }
    }

    setDeliveriesLoading(true)
    void Promise.all(candidates.map(async (session) => {
      try {
        const { messages } = await api.getMessages(session.id)
        const files = changedFiles(messages)
        return files.length > 0 ? { session, files } : null
      } catch {
        return null
      }
    })).then((items) => {
      if (!cancelled) {
        setDeliveries(items.filter((item): item is Delivery => item !== null).slice(0, 4))
        setDeliveriesLoading(false)
      }
    })
    return () => { cancelled = true }
  }, [sessions])

  const selName = selProject ? projects.find((p) => p.id === selProject)?.name : null

  const launch = (text: string) => {
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

  return (
    <section className="view active" data-view="home">
      <div className="reward" {...clickable} onClick={() => toast('打开成长计划')}>
        <span className="ri">🚀</span>做任务赢积分好礼
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M9 6l6 6-6 6" /></svg>
      </div>
      <div className="home-wrap">
        <div className="home-inner">
          <h1 className="hero-title">
            AgentMate<br />
            <span className="g">你的职场超能力</span>
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
                onClick={() => (label === '更多' ? toast('更多快捷入口，敬请期待') : launch(label))}
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

          <div className="comp-zone">
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

          <ProCard className="home-console" aria-label="任务进展" styles={{ body: { display: 'contents' } }}>
            <div className="home-console-head">
              <div>
                <b>任务进展</b>
                <span>从真实会话与执行记录汇总</span>
              </div>
              <WbButton onClick={() => setView('projects')}>查看项目</WbButton>
            </div>
            <div className="home-metrics">
              <ProCard className="home-metric"><Statistic value={activeRuns.length} title="执行中 / 等待输入" /></ProCard>
              <ProCard className="home-metric danger"><Statistic value={recentFailures.length} title="7 天内自动化失败" /></ProCard>
              <ProCard className="home-metric"><Statistic value={deliveries.length} title="最近文件交付" /></ProCard>
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
                }} /> : <Empty className="home-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有需要关注的任务" />}
              </div>
              <div className="home-run-group">
                <h2>最近交付</h2>
                {deliveriesLoading ? <Spin className="home-empty" tip="正在核对最近会话的真实文件变更…" /> : deliveries.length > 0 ? <List dataSource={deliveries} renderItem={({ session, files }) => <List.Item className="home-run-item">
                  <WbButton className="home-run" onClick={() => void openRun(session)}>
                    <span className="home-file-icon">📄</span>
                    <span className="home-run-body">
                      <b>{session.title}</b>
                      <small>{files.slice(0, 2).map(fileName).join('、')}{files.length > 2 ? ` 等 ${files.length} 个文件` : ''}</small>
                    </span>
                    <span className="home-run-arrow">›</span>
                  </WbButton>
                </List.Item>} /> : <Empty className="home-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="最近完成的会话还没有产生文件交付" />}
              </div>
            </div>
          </ProCard>
        </div>
      </div>
    </section>
  )
}
