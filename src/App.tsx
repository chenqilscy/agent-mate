import { lazy, Suspense, useEffect } from 'react'
import { NavigationToggle } from './components/layout/NavigationToggle'
import { Sidebar } from './components/layout/Sidebar'
import { ToastHost } from './components/ui/ToastHost'
import { useUIStore } from './stores/uiStore'
import { useAuthStore } from './stores/authStore'
import { useChatStore } from './stores/chatStore'
import { useSettingsStore } from './stores/settingsStore'
import { api } from './lib/api'
import { readRoute } from './lib/router'
import { useProjectStore } from './stores/projectStore'
import { useSystemSettingsStore } from './stores/systemSettingsStore'
import { useSkillStore } from './stores/skillStore'
import { PageContainer, ProLayout } from '@ant-design/pro-components'
import { Spin } from 'antd'

const HomeView = lazy(() => import('./views/HomeView').then((module) => ({ default: module.HomeView })))
const ChatView = lazy(() => import('./views/ChatView').then((module) => ({ default: module.ChatView })))
const AssistantView = lazy(() => import('./views/AssistantView').then((module) => ({ default: module.AssistantView })))
const ProjectsView = lazy(() => import('./views/ProjectsView').then((module) => ({ default: module.ProjectsView })))
const ProjectHomeView = lazy(() => import('./views/ProjectHomeView').then((module) => ({ default: module.ProjectHomeView })))
const ProjExecView = lazy(() => import('./views/ProjExecView').then((module) => ({ default: module.ProjExecView })))
const ExpertsView = lazy(() => import('./views/ExpertsView').then((module) => ({ default: module.ExpertsView })))
const SkillsView = lazy(() => import('./views/ExpertsView').then((module) => ({ default: module.SkillsView })))
const ConnectorsView = lazy(() => import('./views/ExpertsView').then((module) => ({ default: module.ConnectorsView })))
const AutomationView = lazy(() => import('./views/AutomationView').then((module) => ({ default: module.AutomationView })))
const InspireView = lazy(() => import('./views/InspireView').then((module) => ({ default: module.InspireView })))
const MyFilesView = lazy(() => import('./views/MyFilesView').then((module) => ({ default: module.MyFilesView })))
const KdocsView = lazy(() => import('./views/KdocsView').then((module) => ({ default: module.KdocsView })))
const KnowledgeView = lazy(() => import('./views/KnowledgeView').then((module) => ({ default: module.KnowledgeView })))

function MainView() {
  const view = useUIStore((s) => s.view)
  let content
  switch (view) {
    case 'home':
      content = <HomeView />
      break
    case 'chat':
      content = <ChatView />
      break
    case 'assistant':
      content = <AssistantView />
      break
    case 'projects':
      content = <ProjectsView />
      break
    case 'project':
      content = <ProjectHomeView />
      break
    case 'projexec':
      content = <ProjExecView />
      break
    case 'experts':
      content = <ExpertsView />
      break
    case 'skills':
      content = <SkillsView />
      break
    case 'connectors':
      content = <ConnectorsView />
      break
    case 'automation':
      content = <AutomationView />
      break
    case 'inspire':
      content = <InspireView />
      break
    case 'myfiles':
      content = <MyFilesView />
      break
    case 'kdocs':
      content = <KdocsView />
      break
    case 'knowledge':
      content = <KnowledgeView />
      break
    default:
      content = <HomeView />
  }
  return (
    <PageContainer className="agentmate-page-container">
      <Suspense fallback={<div className="route-loading"><Spin description="正在加载…" /></div>}>
        {content}
      </Suspense>
    </PageContainer>
  )
}

export function App() {
  const navOpen = useUIStore((s) => s.navOpen)
  const setNavOpen = useUIStore((s) => s.setNavOpen)
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)

  useEffect(() => {
    // Bootstrap: who am I, what models exist, what tasks are in the sidebar.
    useAuthStore.getState().load()
    useChatStore.getState().loadSessions()
    void useSkillStore.getState().load()
    api
      .models()
      .then((r) => {
        useSettingsStore.getState().setModels(r.models)
        // WB-136: 不再首屏回填选择——空选择（wb.model='')「跟随默认」，运行时解析到用户在
        // 「配置模型」里设定的账号默认模型（存后端 DB）；配好厂商 key 时后端已自动设默认。
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    const restore = async () => {
      const system = await useSystemSettingsStore.getState().load()
      if (cancelled) return
      let route = readRoute()
      // “默认启动页”只接管根路径；用户显式打开的任何 URL 永远优先。
      if (window.location.pathname === '/' && system.startup_page !== 'home') {
        useUIStore.getState().setView(system.startup_page, { replace: true })
        route = readRoute()
      }
      if (!route.valid) {
        useUIStore.getState().setView('home', { replace: true })
        return
      }
      try {
        if (route.projectId) {
          const project = await api.getProject(route.projectId)
          if (cancelled) return
          useProjectStore.getState().setActive(project)
        }
        if (route.sessionId) {
          await useChatStore.getState().openSession(route.sessionId)
          if (cancelled) return
        } else if (route.view === 'chat') {
          useChatStore.getState().startDraft('对话')
        } else if (route.view === 'projexec' && route.projectId) {
          const project = useProjectStore.getState().active
          useChatStore.getState().startProject(route.projectId, project?.name ?? '项目执行')
        }
        useUIStore.getState().setView(route.view, { history: false })
      } catch {
        const fallback = route.projectId ? 'projects' : 'home'
        useUIStore.getState().setView(fallback, { replace: true })
      }
    }
    void restore()
    window.addEventListener('popstate', restore)
    return () => { cancelled = true; window.removeEventListener('popstate', restore) }
  }, [])

  useEffect(() => {
    // The off-canvas drawer only exists ≤900px. If it was left open when the
    // window widens past the breakpoint, close it — otherwise shrinking back to
    // narrow shows the drawer already open without any user action (WB-021).
    const mq = window.matchMedia('(max-width: 900px)')
    const onChange = (e: MediaQueryListEvent) => {
      // Widened past the breakpoint → the drawer no longer exists, so close it.
      // Narrowed below it → docked-sidebar collapse is a wide-screen concept only,
      // so drop it (else the sidebar stays hidden with no way to reach the drawer).
      if (!e.matches) setNavOpen(false)
      else setSidebarCollapsed(false)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [setNavOpen, setSidebarCollapsed])

  return (
    <ProLayout className="agentmate-pro-shell" pure headerRender={false} menuRender={false} footerRender={false}>
      <div className="win">
        <div className={['shell', navOpen && 'nav-open', sidebarCollapsed && 'sidebar-collapsed'].filter(Boolean).join(' ')}>
          <Sidebar />
          <NavigationToggle />
          {/* Scrim behind the off-canvas sidebar (≤900px); inert at wide widths. */}
          <div className="nav-scrim" aria-hidden="true" onClick={() => setNavOpen(false)} />
          <main className="main" id="main">
            <MainView />
          </main>
        </div>
        <ToastHost />
      </div>
    </ProLayout>
  )
}
