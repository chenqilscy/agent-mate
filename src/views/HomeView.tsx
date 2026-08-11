import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { Space } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { Composer } from '../components/composer/Composer'
import { LoginModal } from '../components/auth/LoginModal'
import { PermPopover } from '../components/composer/PermPopover'
import { TodoDetailModal } from '../components/project/ProjectWork'
import { Popover } from '../components/ui/Popover'
import { WbButton } from '../components/ui/Primitives'
import { startWorkItemRun } from '../lib/sse'
import type { AgentRun, PersonalActionItem, RunStatus, SessionInfo, ViewId, WorkActionSignal, WorkPriority } from '../lib/types'
import { useAuthStore } from '../stores/authStore'
import { useCatalog } from '../stores/catalogStore'
import { useChatStore } from '../stores/chatStore'
import { useConnectivityStore } from '../stores/connectivityStore'
import { useProjectStore } from '../stores/projectStore'
import { useSettingsStore } from '../stores/settingsStore'
import { toast } from '../stores/toastStore'
import { useUIStore } from '../stores/uiStore'
import { useWorkbenchStore } from '../stores/workbenchStore'
import { useWorkItemStore } from '../stores/workItemStore'

const MORE_SHORTCUTS: [ViewId, string, string, string][] = [
  ['skills', '✨', '已安装技能', '管理这台设备可执行的技能'],
  ['connectors', '🔗', '本机连接器', '配置仅保存在本机的连接凭据'],
  ['myfiles', '📁', '本机文件', '查看 Local Agent 工作区文件'],
  ['projects', '☁️', '项目上下文', '从 Server 选择任务执行上下文'],
]

const ACTION_LABEL: Record<WorkActionSignal, string> = {
  overdue: '已逾期',
  due_today: '今天到期',
  blocked: '已阻塞',
  in_progress: '进行中',
  awaiting_acceptance: '待验收',
  starts_today: '今天开始',
  ready: '可以开始',
  urgent: '紧急',
}
const PRIORITY_LABEL: Record<WorkPriority, string> = { '': '未设优先级', low: '低优先级', medium: '中优先级', high: '高优先级', urgent: '紧急' }
const RUN_LABEL: Record<RunStatus, string> = {
  draft: '草稿', planning: '规划中', waiting_approval: '等待授权', paused: '已暂停', accepted: '已验收',
  queued: '排队中', leased: '正在领取', running: '执行中', waiting_user: '等待你的回答', recoverable: '等待恢复',
  completed: '已完成', succeeded: '已完成', failed: '执行失败', cancelled: '已取消',
}
const ACTIVE_RUNS = new Set<RunStatus>(['queued', 'leased', 'planning', 'running', 'waiting_user', 'waiting_approval', 'paused', 'recoverable'])
const RUNNING_RUNS = new Set<RunStatus>(['queued', 'leased', 'planning', 'running'])
const ATTENTION_RUNS = new Set<RunStatus>(['waiting_user', 'waiting_approval', 'paused', 'recoverable'])
type RunFilter = 'all' | 'running' | 'attention' | 'failed'

function latestBySession(runs: AgentRun[]): AgentRun[] {
  const seen = new Set<string>()
  return [...runs]
    .sort((left, right) => (right.updated_at || right.created_at) - (left.updated_at || left.created_at))
    .filter((run) => {
      if (seen.has(run.session_id)) return false
      seen.add(run.session_id)
      return true
    })
}

function relativeTime(value?: number | null): string {
  if (!value) return '刚刚'
  const seconds = Math.max(0, Date.now() / 1000 - value)
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`
  return `${Math.floor(seconds / 86400)} 天前`
}

function runTone(status: RunStatus): string {
  if (status === 'failed') return 'error'
  if (ATTENTION_RUNS.has(status)) return 'waiting'
  return 'running'
}

function actionButtonLabel(item: PersonalActionItem, linkedRun?: AgentRun): string {
  if (item.project.role === 'Viewer') return '查看任务'
  if (item.status === 'review') return '查看验收'
  if (linkedRun && ACTIVE_RUNS.has(linkedRun.status)) return ATTENTION_RUNS.has(linkedRun.status) ? '去处理' : '继续执行'
  return '开始处理'
}

export function HomeView() {
  const startDraft = useChatStore((state) => state.startDraft)
  const startProject = useChatStore((state) => state.startProject)
  const openSession = useChatStore((state) => state.openSession)
  const sessions = useChatStore((state) => state.sessions)
  const loadSessions = useChatStore((state) => state.loadSessions)
  const send = useChatStore((state) => state.send)
  const setView = useUIStore((state) => state.setView)
  const setSettingsOpen = useUIStore((state) => state.setSettingsOpen)
  const loggedIn = useAuthStore((state) => state.loggedIn)
  const localAgent = useConnectivityStore((state) => state.localAgent)
  const localAgentChecked = useConnectivityStore((state) => state.localAgentChecked)
  const serverState = useConnectivityStore((state) => state.server)
  const projects = useProjectStore((state) => state.projects)
  const loadProjects = useProjectStore((state) => state.load)
  const setActiveProject = useProjectStore((state) => state.setActive)
  const loadWorkItems = useWorkItemStore((state) => state.load)
  const perm = useSettingsStore((state) => state.perm)
  const { QUICK } = useCatalog()

  const actionItems = useWorkbenchStore((state) => state.actionItems)
  const unassignedItems = useWorkbenchStore((state) => state.unassignedItems)
  const runs = useWorkbenchStore((state) => state.runs)
  const workbenchLoading = useWorkbenchStore((state) => state.loading)
  const actionError = useWorkbenchStore((state) => state.actionError)
  const runError = useWorkbenchStore((state) => state.runError)
  const workbenchUpdatedAt = useWorkbenchStore((state) => state.updatedAt)
  const loadWorkbench = useWorkbenchStore((state) => state.load)
  const clearWorkbench = useWorkbenchStore((state) => state.clear)

  const [loginOpen, setLoginOpen] = useState(false)
  const [selProject, setSelProject] = useState<string | null>(null)
  const [pop, setPop] = useState<'ws' | 'perm' | null>(null)
  const [moreOpen, setMoreOpen] = useState(false)
  const [runFilter, setRunFilter] = useState<RunFilter>('all')
  const [startingItemId, setStartingItemId] = useState<string | null>(null)
  const [detail, setDetail] = useState<{ itemId: string; canWrite: boolean } | null>(null)
  const wsAnchor = useRef<HTMLButtonElement | null>(null)
  const permAnchor = useRef<HTMLButtonElement | null>(null)
  const moreAnchor = useRef<HTMLElement | null>(null)

  useEffect(() => {
    void loadProjects()
    void loadSessions()
  }, [loadProjects, loadSessions])
  useEffect(() => {
    if (loggedIn) void loadWorkbench()
    else clearWorkbench()
  }, [clearWorkbench, loadWorkbench, loggedIn])

  const sessionsById = useMemo(() => new Map(sessions.map((session) => [session.id, session])), [sessions])
  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects])
  const latestRuns = useMemo(() => latestBySession(runs), [runs])
  const latestRunByWorkItem = useMemo(() => {
    const result = new Map<string, AgentRun>()
    latestRuns.forEach((run) => { if (run.work_item_id && !result.has(run.work_item_id)) result.set(run.work_item_id, run) })
    return result
  }, [latestRuns])
  const sevenDaysAgo = Date.now() / 1000 - 7 * 86400
  const recentFailedRuns = latestRuns.filter((run) => run.status === 'failed' && run.updated_at >= sevenDaysAgo)
  const activeRuns = latestRuns.filter((run) => ACTIVE_RUNS.has(run.status))
  const attentionRuns = activeRuns.filter((run) => ATTENTION_RUNS.has(run.status))
  const reviewItems = actionItems.filter((item) => item.status === 'review')
  const attentionWorkItemIds = new Set(reviewItems.map((item) => item.id))
  const attentionRunRows = attentionRuns.filter((run) => !run.work_item_id || !attentionWorkItemIds.has(run.work_item_id))
  const needsAttention = reviewItems.length + attentionRunRows.length + recentFailedRuns.length

  const filteredRuns = useMemo(() => {
    const candidate = latestRuns.filter((run) => ACTIVE_RUNS.has(run.status) || (run.status === 'failed' && run.updated_at >= sevenDaysAgo))
    if (runFilter === 'running') return candidate.filter((run) => RUNNING_RUNS.has(run.status))
    if (runFilter === 'attention') return candidate.filter((run) => ATTENTION_RUNS.has(run.status))
    if (runFilter === 'failed') return candidate.filter((run) => run.status === 'failed')
    return candidate
  }, [latestRuns, runFilter, sevenDaysAgo])

  const selectedProjectName = selProject ? projectsById.get(selProject)?.name : null
  const promptSuggestions = (QUICK.day || []).filter(([, label]) => label !== '更多').slice(0, 3)

  const launch = (text: string) => {
    if (!loggedIn) {
      setLoginOpen(true)
      toast('请先登录 Server，Local Agent 才能领取任务')
      return
    }
    const title = text.length > 26 ? `${text.slice(0, 26)}…` : text
    if (selProject && selectedProjectName) startProject(selProject, title)
    else startDraft(title)
    setView('chat')
    void send(text)
  }

  const openRun = async (run: AgentRun) => {
    const project = run.project_id ? projectsById.get(run.project_id) : null
    if (project) setActiveProject(project)
    await openSession(run.session_id)
    setView(run.project_id ? 'projexec' : 'chat', {
      projectId: run.project_id ?? undefined,
      sessionId: run.session_id,
    })
  }

  const openActionItem = async (item: PersonalActionItem) => {
    const project = projectsById.get(item.project.id)
    if (!project) {
      toast('当前项目上下文尚未同步，请刷新工作台')
      return
    }
    setActiveProject(project)
    await loadWorkItems(item.project.id)
    if (!useWorkItemStore.getState().items.some((candidate) => candidate.id === item.id)) {
      toast('任务详情读取失败，请稍后重试')
      return
    }
    setDetail({ itemId: item.id, canWrite: item.project.role !== 'Viewer' })
  }

  const startActionItem = async (item: PersonalActionItem) => {
    const linkedRun = latestRunByWorkItem.get(item.id)
    if (item.project.role === 'Viewer' || item.status === 'review') {
      await openActionItem(item)
      return
    }
    if (linkedRun && ACTIVE_RUNS.has(linkedRun.status)) {
      await openRun(linkedRun)
      return
    }
    if (!localAgent) {
      toast('Local Agent 离线，暂时不能开始本机执行')
      return
    }
    if (startingItemId) return
    setStartingItemId(item.id)
    try {
      const started = await startWorkItemRun({
        projectId: item.project.id,
        workItemId: item.id,
        title: item.title,
        description: item.description,
        idempotencyKey: `workbench:${item.id}:${item.updated_at || item.status}`,
      })
      const project = projectsById.get(item.project.id)
      if (project) setActiveProject(project)
      await Promise.all([loadWorkbench(), loadSessions(), openSession(started.session.id)])
      setView('projexec', { projectId: item.project.id, sessionId: started.session.id })
    } catch {
      toast('发起执行失败，请检查 Server 与 Local Agent 状态')
    } finally {
      setStartingItemId(null)
    }
  }

  const refresh = () => {
    void Promise.all([loadWorkbench(), loadSessions(), loadProjects()])
  }

  const openMore = (event: MouseEvent<HTMLElement>) => {
    moreAnchor.current = event.currentTarget
    setMoreOpen(true)
  }

  const renderRun = (run: AgentRun, action = '打开') => {
    const session = sessionsById.get(run.session_id)
    const projectName = run.project_id ? projectsById.get(run.project_id)?.name || 'Server 项目' : '个人任务'
    return (
      <WbButton className="home-run" key={run.id} onClick={() => void openRun(run)} aria-label={`${action}${session?.title || '执行'}，${RUN_LABEL[run.status]}`}>
        <span className={`home-run-dot ${runTone(run.status)}`} />
        <span className="home-run-body">
          <b>{session?.work_item_title || session?.title || '未命名执行'}</b>
          <small>{RUN_LABEL[run.status]} · {projectName} · {relativeTime(run.updated_at)}</small>
        </span>
        <span className="home-run-arrow">›</span>
      </WbButton>
    )
  }

  return (
    <section className="view active" data-view="home">
      <div className="home-wrap">
        <div className="home-inner">
          <div className="home-page-head">
            <div className="home-page-copy">
              <b>个人 Agent 工作台</b>
              <span>决定下一步、介入关键节点，并验收 Agent 交付</span>
            </div>
            <div className={`reward ${localAgentChecked && !localAgent ? 'is-offline' : ''}`} role="status">
              <span className="ri">{localAgent ? '●' : '○'}</span>
              {localAgentChecked ? (localAgent ? 'Local Agent 在线' : 'Local Agent 离线') : '正在检查 Local Agent…'}
            </div>
          </div>

          <div className="home-layout home-workbench-layout">
            <main className="home-workbench-main">
              {!loggedIn ? (
                <ProCard className="home-work-card home-login-card" styles={{ body: { display: 'contents' } }}>
                  <div className="home-login-copy"><b>登录后查看你的真实工作</b><span>Server 保存项目任务、Session、Run 与交付；Local Agent 在这台设备上执行。</span></div>
                  <WbButton className="btn-dark" onClick={() => setLoginOpen(true)}>登录 Server</WbButton>
                </ProCard>
              ) : (
                <>
                  <ProCard className="home-work-card home-attention-card" styles={{ body: { display: 'contents' } }}>
                    <div className="home-card-head">
                      <div><b>需要我处理</b><span>回答、授权、恢复或验收后，Agent 才能继续</span></div>
                      <span className={`home-count ${needsAttention ? 'is-attention' : ''}`}>{needsAttention}</span>
                    </div>
                    {(actionError || runError || serverState.state === 'cached') && (
                      <div className="home-data-warning" role="status">
                        <span>{serverState.state === 'cached' || workbenchUpdatedAt ? 'Server 暂不可达，显示上次同步结果' : actionError || runError}</span>
                        <WbButton onClick={refresh}>重新同步</WbButton>
                      </div>
                    )}
                    <div className="home-attention-list">
                      {reviewItems.slice(0, 3).map((item) => (
                        <div className="home-attention-row" key={`review:${item.id}`}>
                          <span className="home-attention-icon">✓</span>
                          <WbButton className="home-attention-copy" onClick={() => void openActionItem(item)}>
                            <b>{item.title}</b><small>交付待验收 · {item.project.name}</small>
                          </WbButton>
                          <WbButton className="home-inline-action" onClick={() => void openActionItem(item)}>查看验收</WbButton>
                        </div>
                      ))}
                      {attentionRunRows.slice(0, 3).map((run) => (
                        <div className="home-attention-row" key={`run:${run.id}`}>
                          <span className={`home-run-dot ${runTone(run.status)}`} />
                          <WbButton className="home-attention-copy" onClick={() => void openRun(run)}>
                            <b>{sessionsById.get(run.session_id)?.work_item_title || sessionsById.get(run.session_id)?.title || '未命名执行'}</b>
                            <small>{RUN_LABEL[run.status]} · {relativeTime(run.updated_at)}</small>
                          </WbButton>
                          <WbButton className="home-inline-action" onClick={() => void openRun(run)}>去处理</WbButton>
                        </div>
                      ))}
                      {recentFailedRuns.slice(0, 2).map((run) => (
                        <div className="home-attention-row" key={`failed:${run.id}`}>
                          <span className="home-run-dot error" />
                          <WbButton className="home-attention-copy" onClick={() => void openRun(run)}>
                            <b>{sessionsById.get(run.session_id)?.work_item_title || sessionsById.get(run.session_id)?.title || '未命名执行'}</b>
                            <small>执行失败 · {relativeTime(run.updated_at)}</small>
                          </WbButton>
                          <WbButton className="home-inline-action" onClick={() => void openRun(run)}>查看错误</WbButton>
                        </div>
                      ))}
                      {!needsAttention && <div className="home-status-empty"><span>✓</span>当前没有等待你处理的事项</div>}
                    </div>
                  </ProCard>

                  <ProCard className="home-work-card home-actions-card" styles={{ body: { display: 'contents' } }}>
                    <div className="home-card-head">
                      <div><b>我的行动项</b><span>来自 Server 的跨项目 WorkItem，按行动信号排序</span></div>
                      <Space size={8}><span className="home-source-state">{serverState.state === 'cached' ? '缓存' : 'Server 实时'}</span><WbButton className="home-refresh" disabled={workbenchLoading} onClick={refresh}>{workbenchLoading ? '同步中…' : '刷新'}</WbButton></Space>
                    </div>
                    <div className="home-action-list">
                      {actionItems.slice(0, 8).map((item) => {
                        const linkedRun = latestRunByWorkItem.get(item.id)
                        const disabled = startingItemId === item.id || (!localAgent && item.project.role !== 'Viewer' && item.status !== 'review' && !(linkedRun && ACTIVE_RUNS.has(linkedRun.status)))
                        return (
                          <div className="home-action-row" key={item.id}>
                            <WbButton className="home-action-main" onClick={() => void openActionItem(item)}>
                              <span className={`home-action-signal is-${item.action_reason}`}>{ACTION_LABEL[item.action_reason]}</span>
                              <span className="home-action-copy"><b>{item.title}</b><small>{item.project.name} · {PRIORITY_LABEL[item.priority]}{item.due_date ? ` · 截止 ${item.due_date}` : ''}</small></span>
                            </WbButton>
                            <WbButton className="home-action-primary" disabled={disabled} title={disabled ? 'Local Agent 离线，暂时不能开始本机执行' : undefined} onClick={() => void startActionItem(item)}>
                              {startingItemId === item.id ? '启动中…' : actionButtonLabel(item, linkedRun)}
                            </WbButton>
                          </div>
                        )
                      })}
                      {!workbenchLoading && !actionError && actionItems.length === 0 && <div className="home-status-empty"><span>✓</span>今天没有需要处理的已分配任务</div>}
                      {workbenchLoading && actionItems.length === 0 && <div className="home-status-empty is-muted">正在读取 Server 行动项…</div>}
                    </div>
                    {unassignedItems.length > 0 && (
                      <details className="home-unassigned">
                        <summary>可认领任务 <span>{unassignedItems.length}</span></summary>
                        <div className="home-action-list">
                          {unassignedItems.slice(0, 5).map((item) => (
                            <div className="home-action-row" key={item.id}>
                              <WbButton className="home-action-main" onClick={() => void openActionItem(item)}><span className={`home-action-signal is-${item.action_reason}`}>{ACTION_LABEL[item.action_reason]}</span><span className="home-action-copy"><b>{item.title}</b><small>{item.project.name} · 未分配</small></span></WbButton>
                              <WbButton className="home-action-primary" disabled={!localAgent || item.project.role === 'Viewer'} onClick={() => void startActionItem(item)}>认领并处理</WbButton>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </ProCard>
                </>
              )}

              <ProCard className="home-command home-quick-start" styles={{ body: { display: 'contents' } }}>
                <div className="home-card-head"><div><b>快速开始</b><span>提出一个目标，或从真实项目上下文开始</span></div></div>
                <div className="comp-zone">
                  <Composer variant="home" onSend={launch} autoFocus />
                  <div className="ctray">
                    <WbButton className="tray-chip" ref={wsAnchor} onClick={() => setPop((current) => current === 'ws' ? null : 'ws')}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>{selectedProjectName ?? '选择工作空间'}
                    </WbButton>
                    <WbButton className="tray-chip" ref={permAnchor} onClick={() => setPop((current) => current === 'perm' ? null : 'perm')}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>{perm}
                    </WbButton>
                  </div>
                  <Popover open={pop === 'ws'} anchor={wsAnchor.current} dir="down" onClose={() => setPop(null)} minWidth={220}>
                    <div className="pop-item" onClick={() => { setSelProject(null); setPop(null) }}>无（默认空间）{selProject === null && <span className="chk">✓</span>}</div>
                    {projects.length === 0 && <div className="pop-item pop-empty">暂无工作空间</div>}
                    {projects.map((project) => <div className="pop-item" key={project.id} onClick={() => { setSelProject(project.id); setPop(null) }}><span className="pi-ic">🗂️</span>{project.name}{selProject === project.id && <span className="chk">✓</span>}</div>)}
                  </Popover>
                  <Popover open={pop === 'perm'} anchor={permAnchor.current} dir="down" onClose={() => setPop(null)} className="perm-pop" minWidth={232}><PermPopover /></Popover>
                </div>
                <div className="home-prompt-suggestions" aria-label="任务建议">
                  {promptSuggestions.map(([icon, label]) => <WbButton className="qchip" key={label} onClick={() => launch(label)}>{icon} {label}</WbButton>)}
                  <WbButton className="qchip" aria-haspopup="menu" aria-expanded={moreOpen} onClick={openMore}>⋯ 更多能力</WbButton>
                </div>
                <Popover open={moreOpen} anchor={moreAnchor.current} dir="down" onClose={() => setMoreOpen(false)} className="more-shortcuts" minWidth={248}>
                  <div className="more-shortcuts-head">更多能力</div>
                  {MORE_SHORTCUTS.map(([view, icon, label, description]) => <WbButton key={view} role="menuitem" className="pop-item more-shortcut-item" onClick={() => { setMoreOpen(false); setView(view) }}><span className="more-shortcut-icon">{icon}</span><span className="more-shortcut-copy"><b>{label}</b><small>{description}</small></span><span className="more-shortcut-arrow">›</span></WbButton>)}
                </Popover>
              </ProCard>
            </main>

            <aside className="home-console home-run-panel" aria-label="正在执行">
              <div className="home-console-head">
                <div><b>正在执行</b><span>真实 Session / Run 状态</span></div>
                <Space size={4}><WbButton className="home-console-action" onClick={() => setSettingsOpen(true, 'diagnostics')}>执行诊断</WbButton><WbButton className="home-console-action" onClick={() => setSettingsOpen(true, 'runtime')}>运行设置</WbButton></Space>
              </div>
              <div className="home-run-filters" role="group" aria-label="运行状态筛选">
                <WbButton className={runFilter === 'all' ? 'active' : ''} aria-pressed={runFilter === 'all'} onClick={() => setRunFilter('all')}><b>{activeRuns.length}</b><span>活动</span></WbButton>
                <WbButton className={runFilter === 'running' ? 'active' : ''} aria-pressed={runFilter === 'running'} onClick={() => setRunFilter('running')}><b>{activeRuns.filter((run) => RUNNING_RUNS.has(run.status)).length}</b><span>执行中</span></WbButton>
                <WbButton className={runFilter === 'attention' ? 'active' : ''} aria-pressed={runFilter === 'attention'} onClick={() => setRunFilter('attention')}><b>{attentionRuns.length}</b><span>待处理</span></WbButton>
                <WbButton className={runFilter === 'failed' ? 'active' : ''} aria-pressed={runFilter === 'failed'} onClick={() => setRunFilter('failed')}><b>{recentFailedRuns.length}</b><span>失败</span></WbButton>
              </div>
              <div className="home-run-list">
                {filteredRuns.slice(0, 8).map((run) => renderRun(run))}
                {!workbenchLoading && filteredRuns.length === 0 && <div className="home-status-empty is-muted">当前筛选下没有 Run</div>}
                {workbenchLoading && runs.length === 0 && <div className="home-status-empty is-muted">正在读取 Server Run…</div>}
              </div>
            </aside>
          </div>
        </div>
      </div>
      {detail && <TodoDetailModal itemId={detail.itemId} canWrite={detail.canWrite} mode="execute" onClose={() => setDetail(null)} onOpenRun={async (sessionId) => {
        const session = sessionsById.get(sessionId) as SessionInfo | undefined
        const run = latestRuns.find((candidate) => candidate.session_id === sessionId)
        if (run) await openRun(run)
        else {
          await openSession(sessionId)
          setView(session?.project_id ? 'projexec' : 'chat', { projectId: session?.project_id ?? undefined, sessionId })
        }
      }} />}
      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </section>
  )
}
