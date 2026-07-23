import { WbButton } from '../components/ui/Primitives'
import { useEffect, useState } from 'react'
import { toast } from '../stores/toastStore'
import { useProjectStore } from '../stores/projectStore'
import { useUIStore } from '../stores/uiStore'
import { NewProjectModal } from '../components/project/NewProjectModal'
import { MembersModal } from '../components/project/MembersModal'
import { LoginModal } from '../components/auth/LoginModal'
import { ServerConnectModal } from '../components/server/ServerConnectModal'
import { useCatalog } from '../stores/catalogStore'
import { useServerStore } from '../stores/serverStore'
import { api } from '../lib/api'
import type { ProjectInfo } from '../lib/types'
import { Dropdown, Empty, Input, Tag } from 'antd'
import { CompatList as List } from '../components/ui/CompatList'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'

// A shared project (M7 C2) carries the caller's role; owned projects show no badge.
const ROLE_LABEL: Record<string, string> = { Owner: '所有者', Admin: '管理员', Member: '成员', Viewer: '只读' }
type ProjectScope = 'all' | 'server' | 'local'

export function ProjectsView() {
  const projects = useProjectStore((s) => s.projects)
  const load = useProjectStore((s) => s.load)
  const setActive = useProjectStore((s) => s.setActive)
  const setView = useUIStore((s) => s.setView)
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen)
  const [modalOpen, setModalOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<ProjectScope>('all')
  const [membersProject, setMembersProject] = useState<ProjectInfo | null>(null)
  const [loginOpen, setLoginOpen] = useState(false)
  const [serverOpen, setServerOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const { PROJ_TPL } = useCatalog()
  const serverEnabled = useServerStore((s) => s.enabled)
  const serverLinked = useServerStore((s) => s.linked)
  const serverChecked = useServerStore((s) => s.checked)
  const refreshServer = useServerStore((s) => s.refreshStatus)

  useEffect(() => { load() }, [load])
  useEffect(() => { if (!serverChecked) void refreshServer() }, [serverChecked, refreshServer])

  // Open the project workbench (home), not straight into an execution (§11).
  const openProject = (p: ProjectInfo) => {
    setActive(p)
    setView('project', { projectId: p.id })
  }
  const localCount = projects.filter((project) => project.origin !== 'server').length
  const serverCount = projects.length - localCount
  const normalizedQuery = query.trim().toLowerCase()
  const shownProjects = projects.filter((project) => {
    if (scope === 'server' && project.origin !== 'server') return false
    if (scope === 'local' && project.origin === 'server') return false
    return project.name.toLowerCase().includes(normalizedQuery)
  })

  const syncProjects = async () => {
    if (syncing) return
    setSyncing(true)
    try {
      const result = await api.serverPull()
      await load()
      toast(`同步完成 · ${result.synced} 个团队项目`)
    } catch {
      toast('同步失败，请检查 Server 连接')
    } finally {
      setSyncing(false)
    }
  }

  const serverContext = !serverChecked
    ? { title: '正在确认账号与项目同步状态', detail: 'AgentMate 账号统一由 Server 提供。', tone: 'checking' }
    : serverLinked
      ? serverEnabled
        ? { title: `已登录 Server 账号 · ${serverLinked.name}`, detail: '团队项目由 Console/Server 管理；同步会拉取最新项目、成员与计划。', tone: 'linked' }
        : { title: `已登录 Server 账号 · ${serverLinked.name}`, detail: '当前缺少 Server 地址，账号身份来自本地验证缓存；配置后可恢复团队项目同步。', tone: 'attention' }
      : !serverEnabled
        ? { title: 'AgentMate Server 尚未配置', detail: '当前是匿名访客，不是本地账号；配置 Server 后才能登录并同步团队项目。', tone: 'attention' }
        : { title: '尚未登录 AgentMate Server', detail: 'AgentMate 用户统一来自 Server；登录后可同步 Console 项目、成员与计划。', tone: 'attention' }

  return (
    <section className="view active" data-view="projects">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>项目</h1>
            <div className="sub">多人协同，打造超级团队</div>
            <WbButton className="btn-line" onClick={() => setModalOpen(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>新建项目
            </WbButton>
          </div>
          <svg className="ph-illus" viewBox="0 0 300 150" aria-hidden="true">
            <rect width="300" height="150" rx="12" fill="#F4FAF7" />
            <circle cx="70" cy="80" r="22" fill="#CFEADC" opacity=".6" />
            <circle cx="150" cy="70" r="26" fill="#16B37A" opacity=".18" />
            <circle cx="230" cy="82" r="20" fill="#BFE3F5" opacity=".6" />
            <rect x="120" y="30" width="60" height="30" rx="8" fill="#fff" stroke="#DDE7E1" />
            <path d="M132 45h36M132 52h24" stroke="#B7C6BD" strokeWidth="2" />
          </svg>
        </div>

        <div className={`projects-context is-${serverContext.tone}`}>
          <span className="projects-context-dot" aria-hidden="true" />
          <div className="projects-context-copy">
            <b>{serverContext.title}</b>
            <span>{serverContext.detail}</span>
          </div>
          {serverChecked && (
            <div className="projects-context-actions">
              {serverLinked && serverEnabled && <WbButton className="btn-ghost" disabled={syncing} onClick={syncProjects}>{syncing ? '同步中…' : '同步项目'}</WbButton>}
              <WbButton
                className="btn-line"
                onClick={() => {
                  if (!serverEnabled) setSettingsOpen(true, 'runtime')
                  else if (serverLinked) setServerOpen(true)
                  else setLoginOpen(true)
                }}
              >
                {!serverEnabled ? '配置 Server' : serverLinked ? '账号与同步' : '登录 Server'}
              </WbButton>
            </div>
          )}
        </div>

        <div className="sec-row projects-owned">
          <div className="project-scopes" role="group" aria-label="项目范围">
            {([
              ['all', `全部 ${projects.length}`],
              ['server', `团队 ${serverCount}`],
              ['local', `本机 ${localCount}`],
            ] as [ProjectScope, string][]).map(([key, label]) => (
              <WbButton
                key={key}
                className={`project-scope ${scope === key ? 'on' : ''}`.trim()}
                aria-pressed={scope === key}
                onClick={() => setScope(key)}
              >
                {label}
              </WbButton>
            ))}
          </div>
          <Input.Search className="search-box" allowClear placeholder="搜索项目" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <List
          id="myProjList"
          className="projects-list"
          dataSource={shownProjects}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={query ? '没有匹配的项目' : scope === 'server' ? '还没有同步到本机的团队项目' : '还没有项目'}>{scope !== 'server' && <WbButton className="btn-line" onClick={() => setModalOpen(true)}>新建项目</WbButton>}</Empty> }}
          renderItem={(p) => (
            <List.Item className="my-proj" key={p.id} {...clickable} onClick={() => openProject(p)}>
              <span className="my-proj-icon">{p.origin === 'server' ? '☁️' : '🤖'}</span>
              <div className="my-proj-main">
                <div className="my-proj-title">
                  {p.name}
                  <Tag className={`project-source ${p.origin === 'server' ? 'is-server' : ''}`}>{p.origin === 'server' ? '团队项目' : '本机项目'}</Tag>
                  {p.origin === 'server' && p.role && <Tag className="pj-rolebadge sm">{ROLE_LABEL[p.role] || p.role}</Tag>}
                  {!!p.sync_conflicts && <Tag color="warning">同步冲突 {p.sync_conflicts}</Tag>}
                </div>
                <div className={`my-proj-desc ${p.instruction ? '' : 'is-empty'}`.trim()}>{p.instruction || '尚未设置项目指令'}</div>
                <div className="my-proj-meta">
                  <span>添加于 {p.ago}</span>
                  <span>{p.connectors.length + p.experts.length + p.skills.length + p.knowledge_ids.length} 项能力</span>
                  {!!p.connectors.length && <span>{p.connectors.length} 个连接器</span>}
                  {!!p.knowledge_ids.length && <span>{p.knowledge_ids.length} 个知识库</span>}
                </div>
              </div>
              <Dropdown menu={{ items: [{ key: 'open', label: '打开项目' }, { key: 'members', label: '成员管理' }], onClick: ({ key, domEvent }) => { domEvent.stopPropagation(); if (key === 'open') openProject(p); else setMembersProject(p) } }} trigger={['click']}>
                <WbButton className="mp-more" aria-label={`${p.name} 项目菜单`} onClick={(e) => e.stopPropagation()}>⋯</WbButton>
              </Dropdown>
            </List.Item>
          )}
        />

        <div className="sec-title">从模版创建</div>
        <div className="card-grid g4">
          {PROJ_TPL.map(([ic, n, d]) => (
            <ProCard className="tpl" key={n} hoverable {...clickable} onClick={() => setModalOpen(true)} styles={{ body: { display: 'contents' } }}>
              <span className="t-ic">{ic}</span>
              <div>
                <div className="t-n">{n}</div>
                <div className="t-d">{d}</div>
              </div>
            </ProCard>
          ))}
        </div>
      </div>

      <NewProjectModal open={modalOpen} onClose={() => setModalOpen(false)} onCreated={(p) => { setModalOpen(false); openProject(p) }} />
      {membersProject && <MembersModal project={membersProject} onClose={() => setMembersProject(null)} onLeft={() => { setMembersProject(null); void load() }} />}
      {loginOpen && <LoginModal onClose={() => { setLoginOpen(false); void refreshServer() }} />}
      {serverOpen && <ServerConnectModal onClose={() => { setServerOpen(false); void refreshServer(); void load() }} />}
    </section>
  )
}
