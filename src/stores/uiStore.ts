// UI shell state: current view, overview-panel open/close, theme, popover stack.
import { create } from 'zustand'
import type { ViewId } from '../lib/types'

type Theme = 'light' | 'dark'

// 设置中心（WB-146）的标签页 id。顺序即左侧导航顺序。
export type SettingsTab =
  | 'account' | 'system' | 'agent' | 'shortcuts' | 'memory' | 'model'
  | 'assistant' | 'personalize' | 'data' | 'security' | 'help'

interface UIState {
  view: ViewId
  ovOpen: boolean
  theme: Theme
  // popover stack: id of the currently open popover (null = none). One-at-a-time
  // is enough for M1; the Esc-level stack lands with the full popover system.
  openPopover: string | null
  // File viewer (M3): path of the workspace file open in the overview panel.
  viewerPath: string | null
  // Whether the overview panel is expanded to full width.
  ovExpanded: boolean
  // Responsive (≤900px): sidebar collapses to an off-canvas drawer; this is its
  // open state. Ignored at wide widths where the sidebar is always docked.
  navOpen: boolean
  // Wide-screen (>900px) docked-sidebar collapse. Distinct from navOpen (the
  // ≤900px drawer): here the sidebar is fully hidden and re-opened via the
  // menubar hamburger. Reset when the window narrows past 900px (App.tsx).
  sidebarCollapsed: boolean
  // 模型管理弹窗（WB-132）：提到全局，侧栏/账号菜单与输入框模型下拉都能打开同一个。
  modelConfigOpen: boolean
  // 设置中心弹窗（WB-146）：统一多标签设置面板，账号浮层「设置」打开。
  settingsOpen: boolean
  settingsTab: SettingsTab

  setView: (v: ViewId) => void
  toggleOv: () => void
  setOv: (open: boolean) => void
  setTheme: (t: Theme) => void
  setPopover: (id: string | null) => void
  openFile: (path: string) => void
  closeFile: () => void
  toggleExpand: () => void
  setNavOpen: (open: boolean) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setModelConfigOpen: (open: boolean) => void
  setSettingsOpen: (open: boolean, tab?: SettingsTab) => void
  setSettingsTab: (tab: SettingsTab) => void
}

const THEME_KEY = 'wb.theme'

function initialTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY) as Theme | null
  if (saved) return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(t: Theme) {
  document.body.classList.toggle('dark', t === 'dark')
}

const startTheme = initialTheme()
applyTheme(startTheme)

export const useUIStore = create<UIState>((set) => ({
  view: 'home',
  ovOpen: false,
  theme: startTheme,
  openPopover: null,
  viewerPath: null,
  ovExpanded: false,
  navOpen: false,
  sidebarCollapsed: false,
  modelConfigOpen: false,
  settingsOpen: false,
  settingsTab: 'account',

  // Switching views also dismisses the mobile nav drawer (you navigated, so the
  // drawer's job is done) and any open popover.
  setView: (v) => set({ view: v, openPopover: null, navOpen: false }),
  toggleOv: () => set((s) => ({ ovOpen: !s.ovOpen })),
  // Collapsing the panel also drops the expanded state so it reopens at normal width.
  setOv: (open) => set(open ? { ovOpen: true } : { ovOpen: false, ovExpanded: false }),
  setTheme: (t) => {
    localStorage.setItem(THEME_KEY, t)
    applyTheme(t)
    set({ theme: t })
  },
  setPopover: (id) => set((s) => ({ openPopover: s.openPopover === id ? null : id })),
  // Opening a file force-opens the panel (a blue link / artifact card may be
  // clicked while it's collapsed).
  openFile: (path) => set({ viewerPath: path, ovOpen: true }),
  closeFile: () => set({ viewerPath: null }),
  toggleExpand: () => set((s) => ({ ovExpanded: !s.ovExpanded })),
  setNavOpen: (navOpen) => set({ navOpen }),
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  setModelConfigOpen: (modelConfigOpen) => set({ modelConfigOpen }),
  setSettingsOpen: (settingsOpen, tab) => set(tab ? { settingsOpen, settingsTab: tab } : { settingsOpen }),
  setSettingsTab: (settingsTab) => set({ settingsTab }),
}))
