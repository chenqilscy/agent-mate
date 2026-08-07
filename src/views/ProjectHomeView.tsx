import { WbButton, WbTextArea } from '../components/ui/Primitives'
import { useCallback, useEffect, useState } from 'react'
import { api, type Assistant } from '../lib/api'
import type { Automation, ProjectHealth, ProjectInfo, ServerTimelineEvent, SessionInfo, SharedPmPreferences } from '../lib/types'
import { useProjectStore } from '../stores/projectStore'
import { useChatStore } from '../stores/chatStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { Composer } from '../components/composer/Composer'
import { PickerOverlay } from '../components/project/NewProjectModal'
import { PlanWorkspace, TaskList } from '../components/project/ProjectWork'
import { AssetsManager } from '../components/project/AssetsManager'
import { MembersModal } from '../components/project/MembersModal'
import { ProjectBindingsModal, type ProjectBindingKind } from '../components/project/ProjectBindingsModal'
import { ProjectGovernance } from '../components/project/ProjectGovernance'
import { ServerCommentsPanel } from '../components/server/ServerCommentsPanel'
import { useWorkItemStore } from '../stores/workItemStore'
import { useCatalogStore } from '../stores/catalogStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useServerStore } from '../stores/serverStore'
import { skillDisplayName, useSkillStore } from '../stores/skillStore'
import { Alert, Avatar, Breadcrumb, Empty, Progress, Space, Tabs, Tag, Tooltip } from 'antd'
import { CompatList as List } from '../components/ui/CompatList'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'
import { ProjectIdeaPanel } from '../components/ideas/IdeaInbox'

type Tab = '动态' | '计划' | '任务' | '治理' | '资产' | '讨论'
const PROJECT_TABS: Tab[] = ['动态', '计划', '任务', '治理', '资产', '讨论']
type ServerProjectMetadata = {
  fields: number
  sprints: number
  activity: number
  savedViews: number
  reachable: boolean
  preferences: SharedPmPreferences | null
}

function initialProjectTab(): Tab {
  const requested = new URLSearchParams(window.location.search).get('tab')
  return PROJECT_TABS.includes(requested as Tab) ? requested as Tab : '动态'
}
type Kind = 'conn' | 'exp' | 'skill' | 'kb'
const FIELD: Record<Kind, 'connectors' | 'experts' | 'skills' | 'knowledge_ids'> = {
  conn: 'connectors', exp: 'experts', skill: 'skills', kb: 'knowledge_ids',
}

function iconOf(kind: Kind, name: string): string {
  if (kind === 'kb') return '📚'
  const cat = useCatalogStore.getState()
  if (kind === 'conn') return cat.NP_CONNS.find((c) => c[1] === name)?.[0] ?? '🔗'
  if (kind === 'exp') return cat.NP_EXPERTS.find((e) => e[1] === name)?.[0] ?? '🧑'
  const label = skillDisplayName(name)
  return cat.SK_GRID.find((s) => s.name === label || s.slug === name)?.icon ?? '🧩'
}

function relativeTime(timestamp: number): string {
  const seconds = Math.max(0, Date.now() / 1000 - timestamp)
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`
  return `${Math.floor(seconds / 86400)}天前`
}

function projectWriteError(error: unknown): string {
  return String((error as Error)?.message || '').includes('→ 503')
    ? 'Server 暂不可达，本次修改未保存'
    : '保存失败，请重试'
}

const IC_ADD = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
const IC_EDIT = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 14, height: 14 }}><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg>

function ProjectHealthPanel({ health, onOpenGovernance }: { health: ProjectHealth; onOpenGovernance: () => void }) {
  const meta = health.status === 'critical'
    ? { label: '严重', color: 'red', type: 'error' as const }
    : health.status === 'attention'
      ? { label: '需关注', color: 'orange', type: 'warning' as const }
      : { label: '健康', color: 'green', type: 'success' as const }
  return (
    <ProCard className="pj-health">
      <div className="pj-health-head">
        <b>项目健康</b>
        <Tag color={meta.color}>{meta.label}</Tag>
        <span>{health.stale ? 'Server 不可达 · 本机最后同步镜像' : health.source === 'server' ? 'Server 实时计算' : '本机实时计算'}</span>
      </div>
      <Alert
        showIcon
        type={health.stale && health.status === 'healthy' ? 'warning' : meta.type}
        title={health.reasons.length ? health.reasons.map((reason) => `${reason.label} ${reason.count}`).join('；') : '当前没有需要介入的项目风险信号'}
      />
      <div className="pj-health-progress">
        <span>整体进度</span><Progress percent={health.summary.completion_percent} size="small" />
      </div>
      <Space wrap size={[4, 6]}>
        <Tag>阻塞 {health.summary.blocked_tasks}</Tag>
        <Tag>任务逾期 {health.summary.overdue_tasks}</Tag>
        <Tag>里程碑逾期 {health.summary.overdue_milestones}</Tag>
        <Tag color={health.summary.critical_risks ? 'red' : undefined}>严重风险 {health.summary.critical_risks}</Tag>
        <Tag color={health.summary.high_risks ? 'orange' : undefined}>高风险 {health.summary.high_risks}</Tag>
        <Tag>待决策 {health.summary.pending_decisions}</Tag>
        {(health.summary.open_risks || health.summary.pending_decisions) > 0 && <WbButton className="btn-ghost pj-health-link" onClick={onOpenGovernance}>查看治理台账</WbButton>}
      </Space>
    </ProCard>
  )
}

// Project home = a workbench (§11): stable goal tabs + a live 项目配置 sidebar.
// Execution is a sub-item — the composer starts one; the 动态 tab lists them.
export function ProjectHomeView() {
  const active = useProjectStore((s) => s.active)
  const setActive = useProjectStore((s) => s.setActive)
  const reloadProjects = useProjectStore((s) => s.load)
  const projects = useProjectStore((s) => s.projects)
  const setView = useUIStore((s) => s.setView)
  const startProject = useChatStore((s) => s.startProject)
  const openSession = useChatStore((s) => s.openSession)
  const send = useChatStore((s) => s.send)
  const consoleUrl = useServerStore((s) => s.consoleUrl)
  const serverChecked = useServerStore((s) => s.checked)
  const refreshServer = useServerStore((s) => s.refreshStatus)
  useSkillStore((s) => s.builtin)
  useSkillStore((s) => s.installed)

  const [project, setProject] = useState<ProjectInfo | null>(active)
  const [tab, setTab] = useState<Tab>(initialProjectTab)
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [timeline, setTimeline] = useState<ServerTimelineEvent[]>([])
  const [timelineStale, setTimelineStale] = useState(false)
  const [health, setHealth] = useState<ProjectHealth | null>(null)
  const [activityExpanded, setActivityExpanded] = useState(false)
  const [configOpen, setConfigOpen] = useState(false)
  const [editInstr, setEditInstr] = useState(false)
  const [instrDraft, setInstrDraft] = useState('')
  const [picker, setPicker] = useState<Kind | null>(null)
  const [pickerSet, setPickerSet] = useState<Set<string>>(new Set())
  const [membersOpen, setMembersOpen] = useState(false)
  const [bindingPicker, setBindingPicker] = useState<ProjectBindingKind | null>(null)
  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [automations, setAutomations] = useState<Automation[]>([])
  const [bindingsLoaded, setBindingsLoaded] = useState(false)
  const [serverMetadata, setServerMetadata] = useState<ServerProjectMetadata | null>(null)
  const loadWork = useWorkItemStore((s) => s.load)
  const kbs = useKnowledgeStore((s) => s.kbs)
  const kbLoaded = useKnowledgeStore((s) => s.loaded)
  const loadKbs = useKnowledgeStore((s) => s.load)

  const pid = active?.id

  const loadBindings = useCallback(async () => {
    try {
      const [assistantResult, automationResult] = await Promise.all([
        api.listAssistants(),
        api.listAutomations(),
      ])
      setAssistants(assistantResult.assistants)
      setAutomations(automationResult.automations)
      setBindingsLoaded(true)
    } catch {
      setBindingsLoaded(false)
    }
  }, [])

  useEffect(() => {
    if (!pid) return
    // Entering a project is a fresh execution context — drop any ad-hoc loadout the
    // previous chat picked from the ＋ menu, so it can't leak into this project's run
    // (WB-003). Reset happens on entry, before the user picks in the project composer,
    // so the "pick-then-launch" path here is preserved.
    useLoadoutStore.getState().reset()
    api.getProject(pid).then((p) => {
      setProject(p)
      setActive(p)
      useLoadoutStore.getState().setKnowledgeIds(p.knowledge_ids ?? [])
    }).catch(() => {})
    api.projectSessions(pid).then((r) => setSessions(r.sessions)).catch(() => {})
    setActivityExpanded(false)
    setTimelineStale(false)
    api.serverTimeline(pid).then((r) => {
      setTimeline(r.events)
      setTimelineStale(r.server && !r.reachable)
    }).catch(() => { setTimelineStale(active?.origin === 'server') })
    void loadWork(pid).then(() => api.serverSyncConflicts(pid)).then(({ count }) => {
      setProject((current) => current ? { ...current, sync_conflicts: count } : current)
    }).catch(() => {})
    void loadBindings()
  }, [pid, active?.origin, setActive, loadWork, loadBindings])

  useEffect(() => {
    if (!pid || active?.origin !== 'server') {
      setServerMetadata(null)
      return
    }
    if (!serverChecked) void refreshServer()
    let alive = true
    void Promise.allSettled([
      api.serverProjectCustomFields(pid),
      api.serverProjectSprints(pid),
      api.serverProjectActivity(pid),
      api.serverProjectPmPreferences(pid),
    ]).then(([fields, sprints, activity, preferences]) => {
      if (!alive) return
      const fieldCount = fields.status === 'fulfilled' ? fields.value.fields.length : null
      const sprintCount = sprints.status === 'fulfilled' ? sprints.value.sprints.length : null
      const activityCount = activity.status === 'fulfilled' ? activity.value.activity.length : null
      const savedViews = preferences.status === 'fulfilled' ? (preferences.value.preferences.views?.length ?? 0) : null
      const values = [fieldCount, sprintCount, activityCount, savedViews]
      setServerMetadata({
        fields: fieldCount ?? 0,
        sprints: sprintCount ?? 0,
        activity: activityCount ?? 0,
        savedViews: savedViews ?? 0,
        reachable: values.every((value) => value !== null),
        preferences: preferences.status === 'fulfilled' ? preferences.value.preferences : null,
      })
    })
    return () => { alive = false }
  }, [pid, active?.origin, serverChecked, refreshServer])

  useEffect(() => { if (!kbLoaded) void loadKbs() }, [kbLoaded, loadKbs])
  useEffect(() => {
    if (!pid || (tab !== '动态' && tab !== '治理')) return
    api.projectHealth(pid).then(setHealth).catch(() => setHealth(null))
  }, [pid, tab])

  if (!project) return <section className="view active" data-view="project" />

  const applyProject = (p: ProjectInfo) => { setProject(p); setActive(p); reloadProjects() }
  // The caller's role in this project (M7 C2) drives the badge + management access.
  const ROLE_LABEL: Record<string, string> = { Owner: '所有者', Admin: '管理员', Member: '成员', Viewer: '只读' }
  const canManage = project.role === 'Owner' || project.role === 'Admin'
  const canWrite = project.role !== 'Viewer'
  const isShared = !!project.role && project.role !== 'Owner'
  const onLeft = () => { setMembersOpen(false); toast('已退出项目'); reloadProjects(); setView('projects') }

  const saveInstruction = async () => {
    try {
      const p = await api.updateProject(project.id, { instruction: instrDraft })
      setEditInstr(false)
      applyProject(p)
      toast('指令已更新')
    } catch (error) {
      toast(projectWriteError(error))
    }
  }

  const openPicker = (k: Kind) => {
    if (k === 'kb' && project.origin === 'server') { toast('中央项目知识库由 Console 统一管理'); return }
    if (!canManage) { toast('只有管理员或所有者可以修改项目配置'); return }
    setPickerSet(new Set(project[FIELD[k]] ?? []))
    setPicker(k)
  }
  const closePicker = async () => {
    const k = picker!
    try {
      const p = await api.updateProject(project.id, { [FIELD[k]]: [...pickerSet] })
      setPicker(null)
      applyProject(p)
      if (k === 'kb') useLoadoutStore.getState().setKnowledgeIds(p.knowledge_ids ?? [])
      toast('项目配置已更新')
    } catch (error) {
      toast(projectWriteError(error))
    }
  }

  const launch = (text: string) => {
    // 执行计划项时，待办以 🔖 ref 只注入本轮 LLM 输入、不进正文/标题；此时用计划项名
    // 作会话标题，让「动态」feed 能认出执行的是哪个计划项，而非随手指令（WB-047）。
    const todoRef = useLoadoutStore.getState().refs.find((r) => r.kind === 'todo')
    const raw = todoRef?.name ?? text
    startProject(project.id, raw.length > 26 ? raw.slice(0, 26) + '…' : raw)
    setView('projexec', { projectId: project.id })
    void send(text)
  }
  const openExec = (id: string) => { openSession(id); setView('projexec', { projectId: project.id, sessionId: id }) }
  const openConsoleProject = () => {
    if (!consoleUrl) {
      toast('Console 地址尚未就绪，请稍后重试')
      return
    }
    window.open(`${consoleUrl}/projects/${encodeURIComponent(project.id)}`, '_blank', 'noopener,noreferrer')
  }

  const boundAssistants = assistants.filter((item) => item.workspace === `project:${project.id}`)
  const boundAutomations = automations.filter((item) => item.project_id === project.id)
  const localSessions = new Map(sessions.map((session) => [session.id, session]))
  const remoteSessionIds = new Set(timeline.map((event) => event.ext_id).filter(Boolean))
  const activityFeed = [
    ...timeline.map((event) => ({
      id: `server:${event.id}`, title: event.title || event.summary || '项目动态',
      actor: event.actor_name, when: relativeTime(event.created_at), createdAt: event.created_at,
      sessionId: event.ext_id && localSessions.has(event.ext_id) ? event.ext_id : null,
      running: false,
    })),
    ...sessions.filter((session) => !remoteSessionIds.has(session.id)).map((session) => ({
      id: `local:${session.id}`, title: session.title, actor: session.owner_name || '',
      when: session.ago ?? '', createdAt: session.updated_at || session.created_at || 0,
      sessionId: session.id, running: session.status === 'running',
    })),
  ].sort((a, b) => b.createdAt - a.createdAt)
  const visibleActivity = activityExpanded ? activityFeed : activityFeed.slice(0, 12)

  const bindingSection = (kind: ProjectBindingKind, label: string) => {
    const items = kind === 'assistant' ? boundAssistants : boundAutomations
    return (
      <ProCard className="pjcfg-sec" styles={{ body: { display: 'contents' } }}>
        <div className="pjcfg-h">
          {label}<span className="n">{bindingsLoaded ? items.length : '—'}</span>
          {canManage && <span className="add" aria-label={`配置${label}`} {...clickable} onClick={() => setBindingPicker(kind)}>{IC_ADD}</span>}
        </div>
        {items.length ? (
          <Avatar.Group className="pjcfg-icons">
            {items.map((item) => (
              <Tooltip title={item.name} key={item.id}>
                <Avatar className="pjcfg-ic">{kind === 'assistant' ? ((item as Assistant).avatar || '🤖') : '⏰'}</Avatar>
              </Tooltip>
            ))}
          </Avatar.Group>
        ) : (
          <div className="pjcfg-sub">{bindingsLoaded ? (canManage ? '未配置，点 ＋ 添加' : '未配置') : '暂时无法读取配置'}</div>
        )}
      </ProCard>
    )
  }

  const cfgSection = (k: Kind, label: string) => {
    const items = project[FIELD[k]] ?? []
    const labelOf = (name: string) => k === 'kb'
      ? (project.origin === 'server' ? `中央项目知识库 ${name.slice(0, 8)}` : (kbs.find((kb) => kb.id === name)?.name ?? '已删除知识库'))
      : k === 'skill' ? skillDisplayName(name) : name
    return (
      <ProCard className="pjcfg-sec" styles={{ body: { display: 'contents' } }}>
        <div className="pjcfg-h">
          {label}<span className="n">{items.length}</span>
          {canManage && !(k === 'kb' && project.origin === 'server') && <span className="add" {...clickable} onClick={() => openPicker(k)}>{IC_ADD}</span>}
        </div>
        {items.length ? (
          <Avatar.Group className="pjcfg-icons">
            {items.map((n) => <Tooltip title={labelOf(n)} key={n}><Avatar className="pjcfg-ic">{iconOf(k, n)}</Avatar></Tooltip>)}
          </Avatar.Group>
        ) : (
          <div className="pjcfg-sub">{k === 'kb' && project.origin === 'server' ? '由 Console 统一管理' : '未配置，点 ＋ 添加'}</div>
        )}
      </ProCard>
    )
  }

  return (
    <section className="view active" data-view="project">
      <div className="chat-head">
        <div className="pe-crumb">
          <Breadcrumb items={[{ title: <span {...clickable} onClick={() => setView('projects')}>项目</span> }, { title: project.name }]} />
          <Tag className={`project-source ${project.origin === 'server' ? 'is-server' : ''}`}>{project.origin === 'server' ? '团队项目 · Console' : '本机项目'}</Tag>
          {isShared && <Tag className="pj-rolebadge">协作 · {ROLE_LABEL[project.role!] || project.role}</Tag>}
          {!!project.sync_conflicts && <Tooltip title="本地离线改动与 Server 镜像存在分叉，已保留本地版本，请在恢复连接后核对。"><Tag color="warning">同步冲突 {project.sync_conflicts}</Tag></Tooltip>}
          {timelineStale && <Tooltip title="Server 当前不可达；动态展示本机最后一次成功回读的缓存（如有）。"><Tag>动态缓存</Tag></Tooltip>}
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <WbButton className="btn-ghost pjcfg-toggle" style={{ height: 32 }} onClick={() => setConfigOpen(true)}>配置</WbButton>
          <WbButton className="btn-dark" style={{ height: 32 }} onClick={() => setMembersOpen(true)}>{canManage ? '邀请' : '成员'}</WbButton>
        </div>
      </div>

      {project.origin === 'server' && (
        <div className="pj-syncbar" role="status">
          <div className="pj-syncbar-copy">
            <b>团队项目由 Server 统一管理</b>
            <span>{serverMetadata?.reachable === false ? 'Server 暂不可达，以下为已读取的可用信息。' : '字段、Sprint 和活动来自 Server；共享模板、WIP 与保存视图请在 Console 管理。'}</span>
            {serverMetadata && <small>自定义字段 {serverMetadata.fields} · Sprint {serverMetadata.sprints} · 活动 {serverMetadata.activity} · 保存视图 {serverMetadata.savedViews}</small>}
          </div>
          <WbButton className="btn-ghost pj-syncbar-action" onClick={openConsoleProject} disabled={!consoleUrl}>在 Console 打开此项目</WbButton>
        </div>
      )}

      <div className="pjh">
        <div className="pjh-main">
          <Tabs
            className="pjh-tabs"
            activeKey={tab}
            onChange={(key) => setTab(key as Tab)}
            items={PROJECT_TABS.map((key) => ({ key, label: key }))}
          />

          <div className="pjh-body">
            {tab === '治理' && <ProjectGovernance projectId={project.id} canWrite={canWrite} />}
            {tab === '动态' && (
              <>
                <ProjectIdeaPanel project={project} projects={projects} canWrite={canWrite} />
                {health && <ProjectHealthPanel health={health} onOpenGovernance={() => setTab('治理')} />}
                {activityFeed.length ? (
                <>
                  <List dataSource={visibleActivity} renderItem={(item) => (
                    <List.Item
                      className="pj-feed-row" key={item.id}
                      {...(item.sessionId ? clickable : {})}
                      onClick={item.sessionId ? () => openExec(item.sessionId!) : undefined}
                    >
                      <span className="fi"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16v12H5.2L4 17.2z" /></svg></span>
                      <span className="ft">{item.title}</span>
                      <span className="fa">{item.actor ? `${item.actor} · ` : ''}{item.running ? '执行中' : item.when}</span>
                    </List.Item>
                  )} />
                  {activityFeed.length > 12 && (
                    <div className="pj-feed-more">
                      <span>{activityExpanded ? `已显示全部 ${activityFeed.length} 条动态` : `已显示最近 12 条，共 ${activityFeed.length} 条`}</span>
                      <WbButton className="btn-ghost" onClick={() => setActivityExpanded((value) => !value)}>{activityExpanded ? '收起' : '查看全部'}</WbButton>
                    </div>
                  )}
                </>
              ) : (
                <Empty className="pj-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有执行记录。在下方描述任务，开始项目的第一次执行。" />
              )}
              </>
            )}

            {tab === '计划' && <PlanWorkspace canWrite={canWrite} canManage={canManage} sharedProject={project.origin === 'server'} sharedPmPreferences={serverMetadata?.preferences ?? null} />}

            {tab === '任务' && <TaskList canWrite={canWrite} />}

            {tab === '资产' && <AssetsManager scope={{ project: project.id }} canWrite={canWrite} />}

            {tab === '讨论' && <ServerCommentsPanel projectId={project.id} canWrite={canWrite} />}
          </div>

          <div className="chat-foot">
            {canWrite ? (
              <Composer variant="chat" onSend={launch} placeholder={`在「${project.name}」里开始一次执行…`} />
            ) : (
              <Tag className="pj-rolebadge">只读模式 · 可查看项目内容，不能发起执行或修改协作数据</Tag>
            )}
            <div className="disc">内容由 AI 生成，请核实重要信息</div>
          </div>
        </div>

        <div className={`pjcfg-scrim${configOpen ? ' open' : ''}`} aria-label="关闭项目配置" {...clickable} onClick={() => setConfigOpen(false)} />
        <ProCard className={`pjcfg${configOpen ? ' mobile-open' : ''}`} styles={{ body: { display: 'contents' } }}>
          <h3>项目配置</h3>
          <div className="pjcfg-sec">
            <div className="pjcfg-h">
              指令
              {!editInstr && canManage && <span className="add" {...clickable} onClick={() => { setInstrDraft(project.instruction); setEditInstr(true) }}>{IC_EDIT}</span>}
            </div>
            {editInstr ? (
              <>
                <WbTextArea className="pjcfg-ta" aria-label="项目指令" placeholder="项目指令" value={instrDraft} onChange={(e) => setInstrDraft(e.target.value)} autoFocus />
                <div className="pjcfg-edit-f">
                  <WbButton className="btn-ghost" style={{ height: 28, padding: '0 12px' }} onClick={() => setEditInstr(false)}>取消</WbButton>
                  <WbButton className="btn-dark" style={{ height: 28, padding: '0 14px' }} onClick={saveInstruction}>保存</WbButton>
                </div>
              </>
            ) : (
              <div className="pjcfg-instr">{project.instruction || '未设置项目指令，点右上角编辑。'}</div>
            )}
          </div>

          {cfgSection('conn', '连接器')}
          {cfgSection('exp', '专家')}
          {cfgSection('skill', '技能')}
          {cfgSection('kb', '知识库')}
          {bindingSection('assistant', '助手')}
          {bindingSection('automation', '自动化')}

          <div className="pjcfg-sec">
            <div className="pjcfg-h">
              成员
              <span className="add" {...clickable} onClick={() => setMembersOpen(true)}>{canManage ? IC_ADD : IC_EDIT}</span>
            </div>
            <div className="pjcfg-sub">
              {canManage ? '邀请队友、分配角色（所有者/管理员/成员/只读）' : `你的角色：${ROLE_LABEL[project.role!] || project.role}`}
            </div>
          </div>

        </ProCard>
      </div>

      {membersOpen && <MembersModal project={project} onClose={() => setMembersOpen(false)} onLeft={onLeft} />}

      {bindingPicker && (
        <ProjectBindingsModal
          kind={bindingPicker}
          project={project}
          projects={projects}
          onClose={() => setBindingPicker(null)}
          onSaved={(nextAssistants, nextAutomations) => {
            setAssistants(nextAssistants)
            setAutomations(nextAutomations)
            setBindingsLoaded(true)
          }}
          onNavigate={(kind) => {
            setBindingPicker(null)
            setView(kind === 'assistant' ? 'assistant' : 'automation')
          }}
        />
      )}

      {picker && (
        <PickerOverlay
          kind={picker}
          sel={pickerSet}
          onToggle={(n) => setPickerSet((prev) => { const nx = new Set(prev); nx.has(n) ? nx.delete(n) : nx.add(n); return nx })}
          onClose={closePicker}
        />
      )}
    </section>
  )
}
