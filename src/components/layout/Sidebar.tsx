import { WbButton } from '../ui/Primitives'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { useChatStore } from '../../stores/chatStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { useNotificationStore } from '../../stores/notificationStore'
import { toast } from '../../stores/toastStore'
import type { SessionInfo, ViewId } from '../../lib/types'
import { activate, clickable } from '../../lib/a11y'
import { LoginModal } from '../auth/LoginModal'
import { MessageCenter } from './MessageCenter'
import { SettingsModal } from '../settings/SettingsModal'
import { useServerStore } from '../../stores/serverStore'
import { IcBell, IcCompass, IcFolder } from '../../lib/icons'
import { App as AntApp, Badge, Button, Dropdown, Input, Menu, Tooltip } from 'antd'
import { CompatList as List } from '../ui/CompatList'
import type { InputRef } from 'antd'
import { openServerConsole } from '../../lib/console'
import { useConnectivityStore } from '../../stores/connectivityStore'
import { readRoute } from '../../lib/router'

type NavItem = { id: ViewId; label: string; icon: ReactNode; cls?: string }
type NavGroup = { label: string; items: NavItem[] }

const NAV_GROUPS: NavGroup[] = [
  {
    label: '个人工作台',
    items: [
      { id: 'home', label: '工作台', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg> },
      { id: 'projects', label: '项目任务', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /></svg> },
      { id: 'skills', label: '本机能力', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg> },
    ],
  },
]

function activeNav(view: ViewId): ViewId | 'more' {
  if (view === 'inspire' || view === 'myfiles' || view === 'kdocs' || view === 'knowledge') return 'more'
  if (view === 'connectors' || view === 'experts') return 'skills'
  if (view === 'chat') return 'home'
  if (view === 'projexec' || view === 'project') return 'projects'
  return view
}

export function Sidebar() {
  const { modal } = AntApp.useApp()
  const view = useUIStore((s) => s.view)
  const route = readRoute()
  const setView = useUIStore((s) => s.setView)
  const sessions = useChatStore((s) => s.sessions)
  const sessionsLoading = useChatStore((s) => s.sessionsLoading)
  const sessionsError = useChatStore((s) => s.sessionsError)
  const sessionsUpdatedAt = useChatStore((s) => s.sessionsUpdatedAt)
  const activeSessionId = useChatStore((s) => s.activeId)
  const loadSessions = useChatStore((s) => s.loadSessions)
  const openSession = useChatStore((s) => s.openSession)
  const projects = useProjectStore((s) => s.projects)
  const activeProject = useProjectStore((s) => s.active)
  const loadProjects = useProjectStore((s) => s.load)
  const setActiveProject = useProjectStore((s) => s.setActive)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)
  const settingsOpen = useUIStore((s) => s.settingsOpen)
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen)
  const me = useAuthStore((s) => s.me)
  const loggedIn = useAuthStore((s) => s.loggedIn)
  const logout = useAuthStore((s) => s.logout)
  // Server 连接是全局态（账号级），入口放账号菜单——无项目也能首次连接（WB-076）。
  const serverEnabled = useServerStore((s) => s.enabled)
  const serverLinked = useServerStore((s) => s.linked)
  const serverChecked = useServerStore((s) => s.checked)
  const refreshServer = useServerStore((s) => s.refreshStatus)
  const localAgent = useConnectivityStore((s) => s.localAgent)
  const localAgentChecked = useConnectivityStore((s) => s.localAgentChecked)
  const [loginOpen, setLoginOpen] = useState(false)
  const unread = useNotificationStore((s) => s.unread)
  const loadNotifs = useNotificationStore((s) => s.load)
  const [msgOpen, setMsgOpen] = useState(false)

  useEffect(() => { loadProjects() }, [loadProjects])
  useEffect(() => {
    const refresh = () => { void loadSessions() }
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [loadSessions])
  useEffect(() => { if (!serverChecked) void refreshServer() }, [serverChecked, refreshServer])
  // Message center (M7 C4): load on mount + poll lightly so the bell badge stays
  // live even while the center is closed.
  useEffect(() => {
    void loadNotifs()
    const t = setInterval(() => void loadNotifs(), 30_000)
    return () => clearInterval(t)
  }, [loadNotifs])
  const [moreOpen, setMoreOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const footRef = useRef<HTMLDivElement>(null)

  // Header tools (WB-024): task/space search box + status filter menu.
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | 'running'>('all')
  const [showAllTasks, setShowAllTasks] = useState(false)
  const [recentScope, setRecentScope] = useState<'project' | 'all'>(() => route.projectId ? 'project' : 'all')
  const searchRef = useRef<InputRef>(null)

  const act = activeNav(view)
  const contextProjectId = (view === 'projexec' || view === 'project')
    ? route.projectId || activeProject?.id || null
    : null
  const contextProject = contextProjectId
    ? projects.find((project) => project.id === contextProjectId)
      || (activeProject?.id === contextProjectId ? activeProject : null)
    : null
  const contextProjectName = contextProject?.name || '当前项目'
  const selectedSessionId = (
    (view === 'chat' || view === 'projexec') ? activeSessionId : null
  ) ?? route.sessionId ?? null

  useEffect(() => { if (searchOpen) searchRef.current?.focus() }, [searchOpen])
  useEffect(() => {
    setRecentScope(contextProjectId ? 'project' : 'all')
    setShowAllTasks(false)
  }, [contextProjectId])

  // The sidebar history has one ontology: Server-persisted Session/Run records.
  // WorkItems and projects have their own explicit entry instead of sharing
  // misleading task/space/automation counters.
  const q = query.trim().toLowerCase()
  const filtering = q !== '' || filter !== 'all'
  const matchText = (t: string) => !q || t.toLowerCase().includes(q)
  const projectNames = new Map(projects.map((project) => [project.id, project.name]))
  const matchSession = (session: SessionInfo) => {
    const searchable = [
      session.title,
      session.work_item_title || '',
      session.project_id ? projectNames.get(session.project_id) || '' : '',
    ].join(' ')
    return matchText(searchable) && (filter === 'all' || session.status === 'running')
  }
  const projectSessions = contextProjectId
    ? sessions.filter((session) => session.project_id === contextProjectId)
    : []
  const scopedSessions = recentScope === 'project' && contextProjectId ? projectSessions : sessions
  const recentShown = scopedSessions.filter(matchSession)
  const visibleRecent = filtering || showAllTasks ? recentShown : recentShown.slice(0, 12)
  const scopeLabel = (session: SessionInfo) => {
    if (session.project_id) {
      const projectLabel = `项目 · ${projectNames.get(session.project_id) || 'Server 项目'}`
      return session.work_item_title ? `${projectLabel} · 任务 · ${session.work_item_title}` : projectLabel
    }
    if (session.kind === 'automation') return '自动化执行'
    return '临时任务'
  }

  const toggleSearch = () => {
    if (searchOpen) setQuery('') // closing → drop the active filter so the lists come back
    setSearchOpen((v) => !v)
  }

  useEffect(() => {
    if (!profileOpen && !moreOpen) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (footRef.current && footRef.current.contains(t)) return
      if ((t as HTMLElement).closest?.('.profile') || (t as HTMLElement).closest?.('.more-wrap')) return
      setProfileOpen(false)
      setMoreOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [profileOpen, moreOpen])

  // 新建任务: a genuinely fresh start — drop any ad-hoc loadout the previous chat
  // had so the home composer opens clean.
  const newTask = () => {
    useChatStore.getState().startDraft('对话')
    useLoadoutStore.getState().reset()
    setView('home')
  }

  const openTask = (id: string) => {
    const session = sessions.find((item) => item.id === id)
    const projectId = session?.project_id ?? undefined
    const project = projectId ? projects.find((item) => item.id === projectId) : undefined
    const navigate = async () => {
      if (project) setActiveProject(project)
      await openSession(id)
      setView(projectId ? 'projexec' : 'chat', { projectId, sessionId: id })
    }
    if (contextProjectId && projectId && projectId !== contextProjectId) {
      const targetName = project?.name || '目标项目'
      modal.confirm({
        title: `切换到项目“${targetName}”？`,
        content: `此执行不属于当前项目“${contextProjectName}”。切换后将打开对应执行过程。`,
        okText: '切换并打开',
        cancelText: '留在当前项目',
        onOk: navigate,
      })
      return
    }
    void navigate()
  }

  return (
    <aside className="sidebar">
      <div className="sb-head">
        <svg className="sb-logo" viewBox="0 0 40 40" aria-hidden="true">
          <rect x="3" y="5" width="34" height="32" rx="10" fill="#16B37A" />
          <path d="M10 12l4.5 5.5h11L30 12" fill="none" stroke="#0E8A5F" strokeWidth="2.6" strokeLinecap="round" />
          <circle cx="15.5" cy="25" r="2.7" fill="#eafff6" />
          <circle cx="24.5" cy="25" r="2.7" fill="#eafff6" />
        </svg>
        <div className="sb-title">
          <b>AgentMate</b>
        </div>
        <div className="sb-icos">
          <Tooltip title="收起侧栏"><Button type="text" className="sb-ico" aria-label="收起侧栏" onClick={() => setSidebarCollapsed(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>
          </Button></Tooltip>
          <Tooltip title="搜索任务和空间"><Button type="text" className={`sb-ico ${searchOpen || q ? 'on' : ''}`.trim()} aria-label="搜索" aria-pressed={searchOpen} onClick={toggleSearch}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          </Button></Tooltip>
          <Dropdown trigger={['click']} menu={{ selectedKeys: [filter], selectable: true, items: [{ key: 'all', label: '全部' }, { key: 'running', label: '进行中' }], onClick: ({ key }) => setFilter(key as 'all' | 'running') }}>
          <Tooltip title="筛选最近执行"><Button type="text" className={`sb-ico ${filter !== 'all' ? 'on' : ''}`.trim()} aria-label="筛选最近执行">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 5h18l-7 8v6l-4-2v-4z" /></svg>
          </Button></Tooltip>
          </Dropdown>
        </div>
      </div>

      {searchOpen && (
        <div className="sb-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          <Input
            ref={searchRef}
            value={query}
            placeholder="搜索任务 / 空间"
            aria-label="搜索任务或空间"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Escape') { setQuery(''); setSearchOpen(false) } }}
          />
          {query && (
            <WbButton type="button" className="sb-scl" aria-label="清空搜索" onClick={() => { setQuery(''); searchRef.current?.focus() }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </WbButton>
          )}
        </div>
      )}

      <nav className="nav">
        <WbButton type="button" className="sb-new-task" onClick={newTask}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          新建任务
        </WbButton>
        <Menu
          mode="inline"
          selectedKeys={[String(act)]}
          onClick={({ key }) => setView(key as ViewId)}
          items={NAV_GROUPS.map((group) => ({
            type: 'group' as const,
            label: group.label,
            children: group.items.map((item) => ({ key: item.id, icon: <span className="n-ic">{item.icon}</span>, label: item.label, className: `nav-item ${item.cls ?? ''}`.trim() })),
          }))}
        />
        {/* Wrap the trigger + flyout so the menu anchors to the button (WB-042),
            instead of the old hard-coded left:250px; bottom:118px that flung it
            to the sidebar's bottom-right corner. */}
        <section className="nav-group nav-resource" aria-label="文件与知识">
          <Dropdown trigger={['click']} open={moreOpen} onOpenChange={setMoreOpen} menu={{ items: [
            { type: 'group', label: '文件与文档', children: [
              { key: 'myfiles', icon: <IcFolder />, label: '我的文件' },
              { key: 'kdocs', label: '金山文档' },
              { key: 'knowledge', label: '知识库' },
            ] },
            { type: 'group', label: '发现', children: [{ key: 'inspire', label: '灵感' }] },
          ], onClick: ({ key }) => { setView(key as ViewId); setMoreOpen(false) } }}>
          <Button type="text" className={`nav-item ${act === 'more' ? 'active' : ''}`.trim()}>
            <span className="n-ic">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="18" cy="12" r="1.6" /></svg>
            </span>
            文件与知识
          </Button>
          </Dropdown>
        </section>
      </nav>

      <section className="sb-scroll" aria-label="最近执行">
        <div className="sb-recent-head">
          <span>最近执行</span>
          <small>{filtering ? `${recentShown.length}/${scopedSessions.length}` : scopedSessions.length}</small>
          {sessionsError ? <span className="sb-sync cached" title={sessionsError}>缓存</span> : sessionsLoading ? <span className="sb-sync">同步中</span> : sessionsUpdatedAt ? <span className="sb-sync live">实时</span> : null}
          <Tooltip title="刷新最近执行"><Button type="text" className="sb-refresh" aria-label="刷新最近执行" onClick={() => void loadSessions()}>↻</Button></Tooltip>
        </div>
        {contextProjectId && (
          <div className="sb-run-scope" role="group" aria-label="最近执行范围">
            <button type="button" className={recentScope === 'project' ? 'active' : ''} aria-pressed={recentScope === 'project'} onClick={() => { setRecentScope('project'); setShowAllTasks(false) }}>
              当前项目 <small>{projectSessions.length}</small>
            </button>
            <button type="button" className={recentScope === 'all' ? 'active' : ''} aria-pressed={recentScope === 'all'} onClick={() => { setRecentScope('all'); setShowAllTasks(false) }}>
              全部 <small>{sessions.length}</small>
            </button>
          </div>
        )}
        {sessionsError && (
          <div className="sb-state-warning" title={sessionsUpdatedAt ? `上次同步 ${new Date(sessionsUpdatedAt).toLocaleTimeString()}` : sessionsError}>
            {sessionsUpdatedAt ? 'Server 暂不可达，显示上次同步结果' : 'Server 执行记录读取失败'}
          </div>
        )}
        <List
          className="sb-list"
          dataSource={visibleRecent}
          locale={{ emptyText: sessionsLoading ? '正在同步执行记录…' : filtering ? '无匹配执行' : recentScope === 'project' && contextProjectId ? '当前项目暂无执行' : '暂无执行记录' }}
          renderItem={(session) => (
            <List.Item
              className={`sb-task sb-run ${selectedSessionId === session.id ? 'active' : ''}`.trim()}
              aria-current={selectedSessionId === session.id ? 'page' : undefined}
              {...clickable}
              onClick={() => openTask(session.id)}
            >
              <div className="sb-task-copy">
                <span className="tt">{session.title}</span>
                <small>{scopeLabel(session)}</small>
              </div>
              {session.status === 'running' ? <Badge status="processing" /> : <span className="ago">{session.ago}</span>}
            </List.Item>
          )}
        />
        {!filtering && recentShown.length > 12 && <Button type="text" className="sb-show-all" onClick={() => setShowAllTasks((value) => !value)}>{showAllTasks ? '收起最近执行' : `显示全部 ${recentShown.length} 项`}</Button>}
      </section>

      <div className="sb-foot" ref={footRef} {...clickable} onClick={(e) => {
        if ((e.target as HTMLElement).closest('.fic')) return
        setProfileOpen((v) => !v)
        setMoreOpen(false)
      }}>
        <svg className="sb-ava" viewBox="0 0 40 40" aria-hidden="true">
          <circle cx="20" cy="20" r="20" fill="#16B37A" />
          <circle cx="14.5" cy="18" r="2.6" fill="#fff" />
          <circle cx="25.5" cy="18" r="2.6" fill="#fff" />
          <path d="M15 26q5 4 10 0" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
        </svg>
        <span className="name">{me?.name ?? '奇'}</span>
        <div className="fic" aria-label="通知" style={{ position: 'relative' }} onClick={(e) => { e.stopPropagation(); setMsgOpen(true) }} {...activate((e) => { e?.stopPropagation(); setMsgOpen(true) })}>
          <Badge count={unread} size="small"><IcBell /></Badge>
        </div>
        <div className="fic" aria-label="灵感" onClick={(e) => { e.stopPropagation(); setView('inspire') }} {...activate((e) => { e?.stopPropagation(); setView('inspire') })}>
          <IcCompass />
        </div>
      </div>

      {profileOpen && (
        <div className="profile open" role="dialog" aria-label="账号">
          <div className="pf-name">
            {loggedIn ? (me?.name ?? 'Server 用户') : '访客模式'}
            <span {...clickable} aria-label="复制用户名" onClick={() => toast('已复制用户名')}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg></span>
          </div>
          <div className="pf-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg>
            {loggedIn ? (me?.plan ?? '体验版') : '未登录 Server'}{loggedIn && <span className="up">升级</span>}
          </div>
          <div className="pf-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="8" /><path d="M8 12h8M12 8v8" /></svg>
            {localAgentChecked ? (localAgent ? `Local Agent 在线 · WAL ${localAgent.transport.wal.count}` : 'Local Agent 离线') : '正在检查 Local Agent'}
          </div>
          <div className="pf-div" />
          <div className="pf-row" {...clickable} onClick={() => { setSettingsOpen(true, 'account'); setProfileOpen(false) }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3.2" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M6 6l1.4 1.4M16.6 16.6L18 18M18 6l-1.4 1.4M7.4 16.6L6 18" /></svg>设置中心
          </div>
          {loggedIn && serverEnabled && (
            <div className="pf-row" {...clickable} onClick={() => { setProfileOpen(false); void openServerConsole() }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 17H7A5 5 0 017 7h2M15 7h2a5 5 0 010 10h-2M8 12h8" /></svg>
              {serverLinked ? `打开 Server Console · ${serverLinked.name}` : '打开 Server Console'}
            </div>
          )}
          <div className="pf-div" />
          {loggedIn ? (
            <div className="pf-row" {...clickable} onClick={() => { setProfileOpen(false); void logout() }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>退出登录
            </div>
          ) : (
            <div className="pf-row" {...clickable} onClick={() => { setProfileOpen(false); setLoginOpen(true) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3" /></svg>登录 / 注册 Server 账号
            </div>
          )}
        </div>
      )}

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      {msgOpen && <MessageCenter onClose={() => setMsgOpen(false)} />}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </aside>
  )
}
