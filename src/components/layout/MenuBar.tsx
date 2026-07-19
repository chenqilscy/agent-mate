import { platform } from '../../platform'
import { toast } from '../../stores/toastStore'
import { useUIStore } from '../../stores/uiStore'

// Windows-style menubar — kept as DOM (decision A.1): in Tauri this drives a
// borderless window via IPC; on web the controls are best-effort no-ops.
export function MenuBar() {
  const navOpen = useUIStore((s) => s.navOpen)
  const setNavOpen = useUIStore((s) => s.setNavOpen)
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)

  return (
    // data-tauri-drag-region makes the borderless window draggable by the bar;
    // interactive children (buttons) still receive clicks normally.
    <div className="menubar" data-tauri-drag-region>
      <div className="mb-left" data-tauri-drag-region>
        {/* Hamburger — shown ≤900px (CSS) to reveal the off-canvas sidebar, and
            forced visible (.show) on wide screens once the docked sidebar is
            collapsed (WB-024), so it doubles as the re-expand control. */}
        <button
          className={`mb-burger ${sidebarCollapsed ? 'show' : ''}`.trim()}
          aria-label={sidebarCollapsed ? '展开侧栏' : '菜单'}
          onClick={() => (sidebarCollapsed ? setSidebarCollapsed(false) : setNavOpen(!navOpen))}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <svg className="app-ic" viewBox="0 0 40 40" aria-hidden="true">
          <rect x="4" y="6" width="32" height="30" rx="9" fill="#16B37A" />
          <path d="M11 12l4 5h10l4-5" fill="none" stroke="#0E8A5F" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="15.5" cy="24" r="2.4" fill="#eafff6" />
          <circle cx="24.5" cy="24" r="2.4" fill="#eafff6" />
        </svg>
        <b>WorkBuddy</b>
      </div>
      <div className="mb-win">
        <button aria-label="最小化" onClick={() => platform.windowControls.minimize()}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14" /></svg>
        </button>
        <button aria-label="最大化" onClick={() => platform.windowControls.toggleMaximize()}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="5" y="5" width="14" height="14" rx="1" /></svg>
        </button>
        <button
          className="close"
          aria-label="关闭"
          onClick={() => (platform.isDesktop ? platform.windowControls.close() : toast('（演示）关闭窗口'))}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
    </div>
  )
}
