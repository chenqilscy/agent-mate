// UI shell state: current view, overview-panel open/close, theme, popover stack.
import { create } from 'zustand'
import type { ViewId } from '../lib/types'

type Theme = 'light' | 'dark'

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
  // One-shot text to drop into the active Composer input（计划「添加到输入框」用）。
  // Composer consumes it via effect then clears it back to null.
  composerPrefill: string | null

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
  setComposerPrefill: (text: string | null) => void
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
  composerPrefill: null,

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
  setComposerPrefill: (composerPrefill) => set({ composerPrefill }),
}))
