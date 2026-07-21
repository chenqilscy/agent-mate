import { WbButton } from '../ui/Primitives'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { useChatStore } from '../../stores/chatStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { useNotificationStore } from '../../stores/notificationStore'
import { toast } from '../../stores/toastStore'
import type { ProjectInfo, SessionInfo, ViewId } from '../../lib/types'
import { activate, clickable } from '../../lib/a11y'
import { LoginModal } from '../auth/LoginModal'
import { MessageCenter } from './MessageCenter'
import { ServerConnectModal } from '../server/ServerConnectModal'
import { SettingsModal } from '../settings/SettingsModal'
import { useServerStore } from '../../stores/serverStore'
import { IcBell, IcCompass, IcFolder } from '../../lib/icons'
import { Badge, Button, Collapse, Dropdown, Input, Menu, Tooltip } from 'antd'
import { CompatList as List } from '../ui/CompatList'
import type { InputRef } from 'antd'

type NavItem = { id: ViewId; label: string; icon: ReactNode; cls?: string }
type NavGroup = { label: string; items: NavItem[] }

const NAV_GROUPS: NavGroup[] = [
  {
    label: '工作',
    items: [
      { id: 'home', label: '新建任务', cls: 'new', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg> },
      { id: 'assistant', label: '助理', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3a4 4 0 014 4c0 2-2 3-2 5h-4c0-2-2-3-2-5a4 4 0 014-4z" /><path d="M9 17h6M10 20h4" /></svg> },
      { id: 'projects', label: '项目', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /></svg> },
      { id: 'automation', label: '自动化', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 8V4M12 8a4 4 0 100 8 4 4 0 000-8z" /><path d="M12 16v4" /></svg> },
    ],
  },
  {
    label: '能力',
    items: [
      { id: 'experts', label: '专家', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg> },
      { id: 'skills', label: '技能', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg> },
      { id: 'connectors', label: '连接器', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 15l6-6M8 8L6 10a4 4 0 006 6l2-2M16 16l2-2a4 4 0 00-6-6l-2 2" /></svg> },
    ],
  },
]

function activeNav(view: ViewId): ViewId | 'more' {
  if (view === 'inspire' || view === 'myfiles' || view === 'kdocs' || view === 'knowledge') return 'more'
  if (view === 'chat') return 'home'
  if (view === 'projexec' || view === 'project') return 'projects'
  return view
}

export function Sidebar() {
  const view = useUIStore((s) => s.view)
  const setView = useUIStore((s) => s.setView)
  const sessions = useChatStore((s) => s.sessions)
  const openSession = useChatStore((s) => s.openSession)
  const projects = useProjectStore((s) => s.projects)
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
  const [serverOpen, setServerOpen] = useState(false)
  const [loginOpen, setLoginOpen] = useState(false)
  const unread = useNotificationStore((s) => s.unread)
  const loadNotifs = useNotificationStore((s) => s.load)
  const [msgOpen, setMsgOpen] = useState(false)

  useEffect(() => { loadProjects() }, [loadProjects])
  useEffect(() => { if (!serverChecked) void refreshServer() }, [serverChecked, refreshServer])
  // Message center (M7 C4): load on mount + poll lightly so the bell badge stays
  // live even while the center is closed.
  useEffect(() => {
    void loadNotifs()
    const t = setInterval(() => void loadNotifs(), 30_000)
    return () => clearInterval(t)
  }, [loadNotifs])
  // Ad-hoc chats (no project) live under 任务; a workspace-bound automation's runs
  // nest under that 空间 like project executions (WB-045); only unbound automation
  // runs go to the dedicated 自动化 group (WB-041). Mutually exclusive, no dup.
  const adhoc = sessions.filter((s) => !s.project_id && s.kind !== 'automation')
  const sessionsOf = (pid: string) => sessions.filter((s) => s.project_id === pid)
  const autoRuns = sessions.filter((s) => s.kind === 'automation' && !s.project_id) // unbound only; updated_at DESC from the API

  const [moreOpen, setMoreOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const footRef = useRef<HTMLDivElement>(null)

  // Header tools (WB-024): task/space search box + status filter menu.
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | 'running'>('all')
  const [showAllTasks, setShowAllTasks] = useState(false)
  const searchRef = useRef<InputRef>(null)

  const act = activeNav(view)

  useEffect(() => { if (searchOpen) searchRef.current?.focus() }, [searchOpen])

  // Live filtering of the 任务 / 空间 lists. Search matches titles/names; the
  // status filter keeps only running sessions. A project survives when it has a
  // matching child, or (text search only) its own name matches.
  const q = query.trim().toLowerCase()
  const filtering = q !== '' || filter !== 'all'
  const matchText = (t: string) => !q || t.toLowerCase().includes(q)
  const matchSession = (s: SessionInfo) => matchText(s.title) && (filter === 'all' || s.status === 'running')
  const adhocShown = adhoc.filter(matchSession)
  const visibleAdhoc = filtering || showAllTasks ? adhocShown : adhocShown.slice(0, 12)
  // Automation runs can pile up (one per fire); show only the recent few here as a
  // quick-access group — the full per-automation history lives on the 自动化 page.
  const autoMatched = autoRuns.filter(matchSession)
  const autoShown = autoMatched.slice(0, 10)
  const projRows = projects
    .map((p) => {
      const kids = sessionsOf(p.id)
      const kidsShown = filtering ? kids.filter(matchSession) : kids
      const show = !filtering || kidsShown.length > 0 || (filter === 'all' && matchText(p.name))
      return { p, kids, kidsShown, show }
    })
    .filter((r) => r.show)

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
  }

  const openTask = (id: string, target: ViewId = 'chat') => {
    openSession(id)
    let projectId: string | undefined
    if (target === 'projexec') {
      const s = sessions.find((x) => x.id === id)
      const p = s?.project_id ? projects.find((pr) => pr.id === s.project_id) : null
      if (p) { setActiveProject(p); projectId = p.id }
    }
    setView(target, { projectId, sessionId: id })
  }

  const openProject = (p: ProjectInfo) => {
    setActiveProject(p)
    setView('project', { projectId: p.id })
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
          <small>v1.0.0</small>
        </div>
        <div className="sb-icos">
          <Tooltip title="收起侧栏"><Button type="text" className="sb-ico" aria-label="收起侧栏" onClick={() => setSidebarCollapsed(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>
          </Button></Tooltip>
          <Tooltip title="搜索任务和空间"><Button type="text" className={`sb-ico ${searchOpen || q ? 'on' : ''}`.trim()} aria-label="搜索" aria-pressed={searchOpen} onClick={toggleSearch}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          </Button></Tooltip>
          <Dropdown trigger={['click']} menu={{ selectedKeys: [filter], selectable: true, items: [{ key: 'all', label: '全部' }, { key: 'running', label: '进行中' }], onClick: ({ key }) => setFilter(key as 'all' | 'running') }}>
          <Button type="text" className={`sb-ico ${filter !== 'all' ? 'on' : ''}`.trim()} aria-label="筛选">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 5h18l-7 8v6l-4-2v-4z" /></svg>
          </Button>
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
        <Menu
          mode="inline"
          selectedKeys={[String(act)]}
          onClick={({ key }) => { const target = key as ViewId; if (target === 'home') newTask(); setView(target) }}
          items={NAV_GROUPS.map((group) => ({
            type: 'group' as const,
            label: group.label,
            children: group.items.map((item) => ({ key: item.id, icon: <span className="n-ic">{item.icon}</span>, label: item.label, className: `nav-item ${item.cls ?? ''}`.trim() })),
          }))}
        />
        {/* Wrap the trigger + flyout so the menu anchors to the button (WB-042),
            instead of the old hard-coded left:250px; bottom:118px that flung it
            to the sidebar's bottom-right corner. */}
        <section className="nav-group" aria-label="资源">
          <div className="nav-group-label">资源</div>
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
            文件与知识<span className="sub">更多</span>
          </Button>
          </Dropdown>
        </section>
      </nav>

      {/* 任务 + 空间 share one scroll region so long session/project lists stay
          reachable; head/nav above and foot below stay pinned (WB-032). */}
      <Collapse
        ghost
        className="sb-scroll"
        defaultActiveKey={['tasks']}
        items={[
          { key: 'tasks', label: `任务 (${adhocShown.length})`, children: <><List className="sb-list" dataSource={visibleAdhoc} locale={{ emptyText: filtering ? '无匹配任务' : '暂无任务' }} renderItem={(s) => <List.Item className="sb-task" {...clickable} onClick={() => openTask(s.id)}><span className="tt">{s.title}</span>{s.status === 'running' ? <Badge status="processing" /> : <span className="ago">{s.ago}</span>}</List.Item>} />{!filtering && adhocShown.length > 12 && <Button type="text" className="sb-show-all" onClick={() => setShowAllTasks((value) => !value)}>{showAllTasks ? '收起最近任务' : `显示全部 ${adhocShown.length} 项`}</Button>}</> },
          { key: 'spaces', label: `空间 (${projRows.length})`, children: <List className="sb-list" dataSource={projRows} locale={{ emptyText: filtering ? '无匹配空间' : '暂无项目' }} renderItem={({ p, kidsShown }) => <List.Item className="sb-task sb-space" {...clickable} onClick={() => openProject(p)}><IcFolder /><span className="tt">{p.name}</span>{kidsShown.length > 0 && <Badge count={kidsShown.length} />}</List.Item>} /> },
          { key: 'automation', label: `自动化 (${autoMatched.length})`, children: <List className="sb-list" dataSource={autoShown} locale={{ emptyText: filtering ? '无匹配运行' : '暂无自动化运行' }} renderItem={(s) => <List.Item className="sb-task" {...clickable} onClick={() => openTask(s.id)}><span className="tt">{s.title}</span>{s.status === 'running' ? <Badge status="processing" /> : <span className="ago">{s.ago}</span>}</List.Item>} /> },
        ]}
      />

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
        <div className="fic" aria-label="发现" onClick={(e) => { e.stopPropagation(); toast('发现') }} {...activate((e) => { e?.stopPropagation(); toast('发现') })}>
          <IcCompass />
        </div>
      </div>

      {profileOpen && (
        <div className="profile open" role="dialog" aria-label="账号">
          <div className="pf-name">
            {me?.name ?? '奇'}
            <span {...clickable} aria-label="复制用户名" onClick={() => toast('已复制用户名')}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg></span>
          </div>
          <div className="pf-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg>
            {me?.plan ?? '体验版'}<span className="up">升级</span>
          </div>
          <div className="pf-div" />
          <div className="pf-row" {...clickable} onClick={() => { setSettingsOpen(true, 'account'); setProfileOpen(false) }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3.2" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M6 6l1.4 1.4M16.6 16.6L18 18M18 6l-1.4 1.4M7.4 16.6L6 18" /></svg>设置中心
          </div>
          {serverEnabled && (
            <div className="pf-row" {...clickable} onClick={() => { setProfileOpen(false); setServerOpen(true) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 17H7A5 5 0 017 7h2M15 7h2a5 5 0 010 10h-2M8 12h8" /></svg>
              {serverLinked ? `已连接 AgentMate Server · ${serverLinked.name}` : '连接 AgentMate Server'}
            </div>
          )}
          <div className="pf-div" />
          {loggedIn ? (
            <div className="pf-row" {...clickable} onClick={() => { setProfileOpen(false); void logout() }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>退出登录
            </div>
          ) : (
            <div className="pf-row" {...clickable} onClick={() => { setProfileOpen(false); setLoginOpen(true) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3" /></svg>登录 / 注册账号
            </div>
          )}
        </div>
      )}

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      {msgOpen && <MessageCenter onClose={() => setMsgOpen(false)} />}
      {serverOpen && <ServerConnectModal onClose={() => { setServerOpen(false); void refreshServer() }} />}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </aside>
  )
}
