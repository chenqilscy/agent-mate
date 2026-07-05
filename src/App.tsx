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
    default:
      return <HomeView />
  }
}

export function App() {
  const navOpen = useUIStore((s) => s.navOpen)
  const setNavOpen = useUIStore((s) => s.setNavOpen)

  useEffect(() => {
    // Bootstrap: who am I, what models exist, what tasks are in the sidebar.
    useAuthStore.getState().load()
    useChatStore.getState().loadSessions()
    api
      .models()
      .then((r) => {
        useSettingsStore.getState().setModels(r.models)
        // Only seed from the backend default on first visit — otherwise this
        // clobbers the user's saved choice every boot (WB-005).
        if (r.default && !localStorage.getItem('wb.model')) {
          useSettingsStore.getState().setModel(r.default)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    // The off-canvas drawer only exists ≤900px. If it was left open when the
    // window widens past the breakpoint, close it — otherwise shrinking back to
    // narrow shows the drawer already open without any user action (WB-021).
    const mq = window.matchMedia('(max-width: 900px)')
    const onChange = (e: MediaQueryListEvent) => {
      if (!e.matches) setNavOpen(false)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [setNavOpen])

  return (
    <div className="win">
      <MenuBar />
      <div className={`shell ${navOpen ? 'nav-open' : ''}`.trim()}>
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
