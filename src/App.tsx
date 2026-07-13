import { useEffect } from 'react'
import { MenuBar } from './components/layout/MenuBar'
import { Sidebar } from './components/layout/Sidebar'
import { ToastHost } from './components/ui/ToastHost'
import { HomeView } from './views/HomeView'
import { ChatView } from './views/ChatView'
import { AssistantView } from './views/AssistantView'
import { ProjectsView } from './views/ProjectsView'
import { ProjectHomeView } from './views/ProjectHomeView'
import { ProjExecView } from './views/ProjExecView'
import { ExpertsView } from './views/ExpertsView'
import { AutomationView } from './views/AutomationView'
import { InspireView } from './views/InspireView'
import { MyFilesView } from './views/MyFilesView'
import { KdocsView } from './views/KdocsView'
import { KnowledgeView } from './views/KnowledgeView'
import { useUIStore } from './stores/uiStore'
import { useAuthStore } from './stores/authStore'
import { useChatStore } from './stores/chatStore'
import { useSettingsStore } from './stores/settingsStore'
import { api } from './lib/api'

function MainView() {
  const view = useUIStore((s) => s.view)
  switch (view) {
    case 'home':
      return <HomeView />
    case 'chat':
      return <ChatView />
    case 'assistant':
      return <AssistantView />
    case 'projects':
      return <ProjectsView />
    case 'project':
      return <ProjectHomeView />
    case 'projexec':
      return <ProjExecView />
    case 'experts':
      return <ExpertsView />
    case 'automation':
      return <AutomationView />
    case 'inspire':
      return <InspireView />
    case 'myfiles':
      return <MyFilesView />
    case 'kdocs':
      return <KdocsView />
    case 'knowledge':
      return <KnowledgeView />
    default:
      return <HomeView />
  }
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
    <div className="win">
      <MenuBar />
      <div className={['shell', navOpen && 'nav-open', sidebarCollapsed && 'sidebar-collapsed'].filter(Boolean).join(' ')}>
        <Sidebar />
        {/* Scrim behind the off-canvas sidebar (≤900px); inert at wide widths. */}
        <div className="nav-scrim" onClick={() => setNavOpen(false)} />
        <main className="main" id="main">
          <MainView />
        </main>
      </div>
      <ToastHost />
    </div>
  )
}
