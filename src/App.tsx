import { useEffect } from 'react'
import { MenuBar } from './components/layout/MenuBar'
import { Sidebar } from './components/layout/Sidebar'
import { ToastHost } from './components/ui/ToastHost'
import { HomeView } from './views/HomeView'
import { ChatView } from './views/ChatView'
import { AssistantView } from './views/AssistantView'
import { ProjectsView } from './views/ProjectsView'
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
  useEffect(() => {
    // Bootstrap: who am I, what models exist, what tasks are in the sidebar.
    useAuthStore.getState().load()
    useChatStore.getState().loadSessions()
    api
      .models()
      .then((r) => {
        useSettingsStore.getState().setModels(r.models)
        if (r.default) useSettingsStore.getState().setModel(r.default)
      })
      .catch(() => {})
  }, [])

  return (
    <div className="win">
      <MenuBar />
      <div className="shell">
        <Sidebar />
        <main className="main" id="main">
          <MainView />
        </main>
      </div>
      <ToastHost />
    </div>
  )
}
