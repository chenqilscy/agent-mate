import { useUIStore } from '../../stores/uiStore'

// The full-width menubar is intentionally gone. This edge handle only appears
// when the responsive drawer is closed or the docked sidebar was collapsed, so
// navigation always remains recoverable without reserving a title-bar row.
export function NavigationToggle() {
  const navOpen = useUIStore((s) => s.navOpen)
  const setNavOpen = useUIStore((s) => s.setNavOpen)
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)

  const openSidebar = () => {
    if (sidebarCollapsed) setSidebarCollapsed(false)
    else setNavOpen(!navOpen)
  }

  return (
    <button className="shell-nav-toggle" aria-label="打开侧栏" onClick={openSidebar}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16M13 9l3 3-3 3" />
      </svg>
    </button>
  )
}
