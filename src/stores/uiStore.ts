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

  setView: (v: ViewId) => void
  toggleOv: () => void
  setOv: (open: boolean) => void
  setTheme: (t: Theme) => void
  setPopover: (id: string | null) => void
  openFile: (path: string) => void
  closeFile: () => void
  toggleExpand: () => void
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

  setView: (v) => set({ view: v, openPopover: null }),
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
}))
