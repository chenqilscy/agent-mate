import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useUIStore } from '../../stores/uiStore'
import { useChatStore } from '../../stores/chatStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useProjectStore } from '../../stores/projectStore'
import { useAuthStore } from '../../stores/authStore'
import { useNotificationStore } from '../../stores/notificationStore'
import { toast } from '../../stores/toastStore'
import type { ProjectInfo, SessionInfo, ViewId } from '../../lib/types'
import { activate } from '../../lib/a11y'
import { LoginModal } from '../auth/LoginModal'
import { MessageCenter } from './MessageCenter'
import { ServerConnectModal } from '../server/ServerConnectModal'
import { SettingsModal } from '../settings/SettingsModal'
import { useServerStore } from '../../stores/serverStore'
import { IcBell, IcCompass, IcFolder } from '../../lib/icons'

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
  const [tasksOpen, setTasksOpen] = useState(true)
  const [spacesOpen, setSpacesOpen] = useState(true)
  const [autoOpen, setAutoOpen] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const footRef = useRef<HTMLDivElement>(null)

  // Header tools (WB-024): task/space search box + status filter menu.
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [filter, setFilter] = useState<'all' | 'running'>('all')
  const searchRef = useRef<HTMLInputElement>(null)

  const act = activeNav(view)

  useEffect(() => { if (searchOpen) searchRef.current?.focus() }, [searchOpen])

  useEffect(() => {
    if (!filterOpen) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (t.closest?.('.sb-fmenu') || t.closest?.('[data-filter-toggle]')) return
      setFilterOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [filterOpen])

  // Live filtering of the 任务 / 空间 lists. Search matches titles/names; the
  // status filter keeps only running sessions. A project survives when it has a
  // matching child, or (text search only) its own name matches.
  const q = query.trim().toLowerCase()
  const filtering = q !== '' || filter !== 'all'
  const matchText = (t: string) => !q || t.toLowerCase().includes(q)
  const matchSession = (s: SessionInfo) => matchText(s.title) && (filter === 'all' || s.status === 'running')
  const adhocShown = adhoc.filter(matchSession)
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
    setExpanded((prev) => new Set(prev).add(p.id))
  }
  const toggleExpand = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const chevron = (open: boolean) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transition: 'transform .15s', transform: open ? 'none' : 'rotate(-90deg)' }}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  )

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
          <div className="sb-ico" aria-label="收起侧栏" onClick={() => setSidebarCollapsed(true)} {...activate(() => setSidebarCollapsed(true))}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>
          </div>
          <div className={`sb-ico ${searchOpen || q ? 'on' : ''}`.trim()} aria-label="搜索" aria-pressed={searchOpen} onClick={toggleSearch} {...activate(toggleSearch)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          </div>
          <div
            className={`sb-ico ${filter !== 'all' ? 'on' : ''}`.trim()}
            data-filter-toggle
            aria-label="筛选"
            aria-haspopup="menu"
            aria-expanded={filterOpen}
            onClick={() => setFilterOpen((v) => !v)}
            {...activate(() => setFilterOpen((v) => !v))}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 5h18l-7 8v6l-4-2v-4z" /></svg>
          </div>
          {filterOpen && (
            <div className="sb-fmenu">
              {([['all', '全部'], ['running', '进行中']] as const).map(([v, label]) => (
                <WbButton
                  key={v}
                  type="button"
                  className={`more-item ${filter === v ? 'sel' : ''}`.trim()}
                  onClick={() => { setFilter(v); setFilterOpen(false) }}
                >
                  {label}
                </WbButton>
              ))}
            </div>
          )}
        </div>
      </div>

      {searchOpen && (
        <div className="sb-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          <WbInput
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
        {NAV_GROUPS.map((group) => (
          <section className="nav-group" aria-label={group.label} key={group.label}>
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((n) => (
              <div
                key={n.id}
                className={`nav-item ${n.cls ?? ''} ${act === n.id ? 'active' : ''}`.trim()}
                onClick={() => { if (n.id === 'home') newTask(); setView(n.id) }}
                {...activate(() => { if (n.id === 'home') newTask(); setView(n.id) })}
              >
                <span className="n-ic">{n.icon}</span>
                {n.label}
              </div>
            ))}
          </section>
        ))}
        {/* Wrap the trigger + flyout so the menu anchors to the button (WB-042),
            instead of the old hard-coded left:250px; bottom:118px that flung it
            to the sidebar's bottom-right corner. */}
        <section className="nav-group" aria-label="资源">
          <div className="nav-group-label">资源</div>
          <div className="more-wrap">
          <div
            className={`nav-item ${act === 'more' ? 'active' : ''}`.trim()}
            onClick={() => setMoreOpen((v) => !v)}
            {...activate(() => setMoreOpen((v) => !v))}
          >
            <span className="n-ic">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="18" cy="12" r="1.6" /></svg>
            </span>
            文件与知识<span className="sub">更多</span>
          </div>
          {moreOpen && (
            <div className="more-menu open">
              <div className="more-group-label">文件与文档</div>
              <div className="more-item" onClick={() => { setView('myfiles'); setMoreOpen(false) }}>
                <IcFolder />我的文件
              </div>
              <div className="more-item" onClick={() => { setView('kdocs'); setMoreOpen(false) }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>金山文档
              </div>
              <div className="more-item" onClick={() => { setView('knowledge'); setMoreOpen(false) }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 5a2 2 0 012-2h9v16H6a2 2 0 00-2 2z" /><path d="M15 3h3a1 1 0 011 1v15" /><path d="M8 7h4M8 11h4" /></svg>知识库
              </div>
              <div className="more-group-label split">发现</div>
              <div className="more-item" onClick={() => { setView('inspire'); setMoreOpen(false) }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" /></svg>灵感
              </div>
            </div>
          )}
          </div>
        </section>
      </nav>

      {/* 任务 + 空间 share one scroll region so long session/project lists stay
          reachable; head/nav above and foot below stay pinned (WB-032). */}
      <div className="sb-scroll">
      <div className="sb-sec" onClick={() => setTasksOpen((v) => !v)} {...activate(() => setTasksOpen((v) => !v))}>
        任务 ({adhocShown.length}) {chevron(tasksOpen)}
      </div>
      {tasksOpen && (
        <div className="sb-list">
          {adhocShown.length === 0 && (
            <div className="sb-task" style={{ color: 'var(--text-3)', cursor: 'default' }}>
              <span className="tt">{filtering ? '无匹配任务' : '暂无任务'}</span>
            </div>
          )}
          {adhocShown.map((s) => (
            <div className="sb-task" key={s.id} onClick={() => openTask(s.id)} {...activate(() => openTask(s.id))}>
              <span className="tt">{s.title}</span>
              {s.status === 'running' ? <span className="dot" /> : <span className="ago">{s.ago}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="sb-sec" onClick={() => setSpacesOpen((v) => !v)} {...activate(() => setSpacesOpen((v) => !v))}>
        空间 ({projRows.length}) {chevron(spacesOpen)}
      </div>
      {spacesOpen && (
        <div className="sb-list">
          {projRows.length === 0 && (
            <div className="sb-task" style={{ color: 'var(--text-3)', cursor: 'default' }}>
              <span className="tt">{filtering ? '无匹配空间' : '暂无项目'}</span>
            </div>
          )}
          {projRows.map(({ p, kids, kidsShown }) => {
            // While filtering, auto-reveal matching children; otherwise honour the
            // manual expand toggle.
            const open = filtering ? kidsShown.length > 0 : expanded.has(p.id)
            return (
              <div key={p.id}>
                <div className="sb-task" onClick={() => openProject(p)} {...activate(() => openProject(p))}>
                  <IcFolder />
                  <span className="tt">{p.name}</span>
                  <span
                    className="sb-chev"
                    aria-label={open ? '收起' : '展开'}
                    onClick={(e) => { e.stopPropagation(); toggleExpand(p.id) }}
                    {...activate((e) => { e?.stopPropagation(); toggleExpand(p.id) })}
                  >
                    {chevron(open)}
                  </span>
                </div>
                {open && kidsShown.map((s) => (
                  <div className="sb-task sb-sub" key={s.id} onClick={() => openTask(s.id, 'projexec')} {...activate(() => openTask(s.id, 'projexec'))}>
                    <span className="tt">{s.title}</span>
                    {s.status === 'running' ? <span className="dot" /> : <span className="ago">{s.ago}</span>}
                  </div>
                ))}
                {open && !filtering && kids.length === 0 && (
                  <div className="sb-task sb-sub" style={{ color: 'var(--text-3)', cursor: 'default' }}>
                    <span className="tt">暂无执行</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Automation runs (WB-041): reachable in one place regardless of workspace,
          capped to the recent few so a frequent schedule can't flood the sidebar. */}
      <div className="sb-sec" onClick={() => setAutoOpen((v) => !v)} {...activate(() => setAutoOpen((v) => !v))}>
        自动化 ({autoMatched.length}) {chevron(autoOpen)}
      </div>
      {autoOpen && (
        <div className="sb-list">
          {autoShown.length === 0 && (
            <div className="sb-task" style={{ color: 'var(--text-3)', cursor: 'default' }}>
              <span className="tt">{filtering ? '无匹配运行' : '暂无自动化运行'}</span>
            </div>
          )}
          {autoShown.map((s) => (
            <div className="sb-task" key={s.id} onClick={() => openTask(s.id)} {...activate(() => openTask(s.id))}>
              <span className="tt">{s.title}</span>
              {s.status === 'running' ? <span className="dot" /> : <span className="ago">{s.ago}</span>}
            </div>
          ))}
          {autoMatched.length > autoShown.length && (
            <div className="sb-task" style={{ color: 'var(--text-3)' }} onClick={() => setView('automation')} {...activate(() => setView('automation'))}>
              <span className="tt">…更多 {autoMatched.length - autoShown.length} 条 · 见自动化页</span>
            </div>
          )}
        </div>
      )}
      </div>

      <div className="sb-foot" ref={footRef} onClick={(e) => {
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
          {unread > 0 && <span className="bell-dot" />}
          <IcBell />
        </div>
        <div className="fic" aria-label="发现" onClick={(e) => { e.stopPropagation(); toast('发现') }} {...activate((e) => { e?.stopPropagation(); toast('发现') })}>
          <IcCompass />
        </div>
      </div>

      {profileOpen && (
        <div className="profile open" role="dialog" aria-label="账号">
          <div className="pf-name">
            {me?.name ?? '奇'}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" onClick={() => toast('已复制用户名')}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg>
          </div>
          <div className="pf-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg>
            {me?.plan ?? '体验版'}<span className="up">升级</span>
          </div>
          <div className="pf-div" />
          <div className="pf-row" onClick={() => { setSettingsOpen(true, 'account'); setProfileOpen(false) }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3.2" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M6 6l1.4 1.4M16.6 16.6L18 18M18 6l-1.4 1.4M7.4 16.6L6 18" /></svg>设置中心
          </div>
          {serverEnabled && (
            <div className="pf-row" onClick={() => { setProfileOpen(false); setServerOpen(true) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 17H7A5 5 0 017 7h2M15 7h2a5 5 0 010 10h-2M8 12h8" /></svg>
              {serverLinked ? `已连接 AgentMate Server · ${serverLinked.name}` : '连接 AgentMate Server'}
            </div>
          )}
          <div className="pf-div" />
          {loggedIn ? (
            <div className="pf-row" onClick={() => { setProfileOpen(false); void logout() }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>退出登录
            </div>
          ) : (
            <div className="pf-row" onClick={() => { setProfileOpen(false); setLoginOpen(true) }}>
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
